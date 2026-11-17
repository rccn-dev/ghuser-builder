# Validating a release

What a developer does in the dev loop, and what the canvas must then do, is one table:
[`tests/scenarios.py`](../tests/scenarios.py). It runs at three levels, each closer to
Rhino than the last. What no script can reach (the toolbar, which Grasshopper reads only
at startup; icons; installing a package) is a manual checklist.

| Level | Runs | Where | Proves |
| --- | --- | --- | --- |
| 1. headless | `uv run --no-project --with pytest pytest tests` | every push: GitLab, and GitHub on Linux, macOS and Windows | staging, stamps, the stale check, deploy's notes, RELOAD, links and junctions, on a stand-in canvas ([`tests/canvas.py`](../tests/canvas.py)) |
| 2. Docker | `GHUSER_TEST_IMAGE=<image> uv run --no-project --with pytest pytest tests/test_dev_scenarios.py` | every push: GitHub, amd64, image built from the commit; locally on arm64 | the same scenarios built for real through the tar stream, each `.ghuser` verified against the code level 1 ran; quick edits build what is on disk |
| 3. Rhino | `uv run tests/rhino/run_scenarios.py --image <image>` | by hand, before a release, on macOS and Windows, Rhino 8 running | the same scenarios in Grasshopper: the label and reason on the component, RELOAD as Rhino runs it, a saved and reopened `.gh` |
| 4. manual | the checklist below | by hand, before a release, on macOS and Windows | the toolbar, icons, the link after a restart, the `.yak`, Docker's messages |

The template's scripts have their own tests (`scripts/tests` in ghuser-template, with
Docker played by the tests), run by its CI on all three systems.

## The scenarios

A project with two components, A and B, deployed, both placed. Then:

| Scenario | deploy says | placed before | placed after |
| --- | --- | --- | --- |
| rebuild, nothing changed | nothing | runs | runs |
| core edit (`src/`) | nothing | runs, new core | runs, new core |
| core edit with an installed `.yak`'s core already loaded | nothing ("Rhino had …") | runs, the `src/` core | runs, the `src/` core |
| `code.py` edit, or a comment only | A: code.py changed | A `dev: replace` | runs |
| `code.py` edited, then reverted | A: code.py changed | runs | runs |
| `metadata.json` or `icon.png` edit | A: restart Rhino, then replace | A `dev: restart, replace` | runs |
| component added | new | runs | runs |
| component removed / renamed | removed (+ new) | B `dev: removed` | runs |
| project moved | code.py changed | `dev: not deployed` | runs |
| ghuser-builder upgraded | code.py changed | `dev: replace` | runs |
| `dev.py uninstall` | | `dev: not deployed` | |

"Placed before" holds both right after deploy (which reloads a running Rhino) and after
the file is saved, closed and reopened. When the top of `code.py` fails first (the project
moved, so its `src/` is gone), Rhino shows its own error, but the label is there.

## Before a release

1. CI green: GitLab (image, examples, level 1) and GitHub (level 1 on three systems, level 2).
2. On a Mac and on a Windows lab PC, each with Rhino 8 and Docker:
   ```
   docker build -t ghuser-builder:check <this checkout>
   uv run tests/rhino/run_scenarios.py --image ghuser-builder:check      # "all scenarios ok in Rhino"
   ```
3. The manual checklist, on both.
4. Record each in the README's Status table: date, system, Rhino version, Docker.

## Manual checklist

From a new project made from ghuser-template, with `[tool.ghuser] builder` set to the
release candidate (or `GHUSER_BUILDER_SRC=<this checkout>`). Each step says what passes.

1. **Toolbar after a restart.** `uv run scripts/dev.py`, then start Rhino and Grasshopper.
   *Pass:* the components are in their tab, with their icons, once each.
   `uv run scripts/dev.py status` says nothing wrong.
2. **The toolbar is read at startup.** Change an input's `description` in a
   `metadata.json`, run `dev.py` with Rhino open, place that component from the toolbar.
   *Pass:* it is stopped with `dev: restart, replace` (the toolbar still has the old
   build). Restart Rhino, place it again: it runs and shows the new description.
   If the first placement already runs with the new description, Grasshopper reads the
   file when placing: report it, since the message then asks for more than is needed.
3. **Icons on the canvas.** *Pass:* a placed component shows its own icon, not the
   default script icon (the default only with `--builder rhino`).
4. **The `.yak`.** `dev.py uninstall`, `uv run scripts/ghuser.py --version 0.1.0`, drag
   the `.yak` onto Rhino, restart. *Pass:* the components come from the ribbon and run;
   a `.gh` saved during development shows `dev: not deployed` on its components until
   they are replaced. Uninstall the package in the Package Manager afterwards.
5. **Docker's messages.** Quit Docker (Docker Desktop, OrbStack, or `colima stop`) and
   run `dev.py`. *Pass:* it names that Docker and says how to start it.
6. **Windows only.** In `%APPDATA%\Grasshopper\UserObjects` the link is a `<JUNCTION>`;
   `dev.py uninstall` removes it and leaves `dist-dev\` in place.

Anything that fails: note the output, the system and the Rhino version in an issue.
