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
4. Record each in the Status table below: date, system, Rhino version, Docker.

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

## Status: what has been checked

Update this after every release check: system, Rhino version, date.

| Claim | Checked |
| --- | --- |
| dev-loop scenarios (`tests/scenarios.py`: core, `code.py`, metadata, icon, added, removed, renamed, moved, upgraded, uninstalled) | ✅ headless (`tests/test_dev_scenarios.py`); ✅ Docker, arm64 (colima); ✅ Docker, amd64 (GitHub); ✅ headless on Windows and macOS (GitHub); ✅ Rhino 8.37, macOS (`tests/rhino/run_scenarios.py`), 2026-11-17; ❓ Rhino on Windows |
| a component whose top level fails (its `src/` gone) keeps its `dev:` label | ✅ Rhino 8.37, macOS |
| image builds (arm64, Docker 27); examples build, verify and package | ✅ `tests/run_examples.sh` |
| verifier rejects a mismatched `.ghuser`, and one without a canvas icon | ✅ same script |
| `local/ghuser_dev.py` with Rhino 8.36 (.NET 10) on macOS (arm64) | ✅ example 02 with `--env src` |
| `ghuser_dev.py deploy` reload: drops `--env` modules, recompiles, recomputes, flags stale canvas code | ✅ example 02 in Rhino 8.36; a core imported at the top of `code.py`, with typed inputs, in Rhino 8.37 |
| reload drops a core of the same name left by an installed `.yak` | ✅ Rhino 8.37, macOS |
| `ghuser_dev.py --builder docker` (tar stream) and `ghuser-build --env` | ✅ macOS, colima with sshfs (5 quick size-changing edits, all verified); `tests/run_examples.sh` |
| `ghuser_dev.py` link, backup, status, uninstall | ✅ `tests/test_ghuser_dev.py` (symlinks) |
| `ghuser_dev.py` on Windows: junction, `%APPDATA%` paths, `rhinocode.exe`, Rhino's Python | ✅ lab PC, 1.1.0 (ghuser-template's dev loop); ✅ lab PC, 1.2.1, ghuser-template's dev loop by hand, 2026-11-18; ❓ `tests/rhino/run_scenarios.py` |
| `templates/local/ghuser.py` (superseded) | ✅ macOS; ❌ Windows |
| Grasshopper loads user objects through a symlinked folder | ❓ not yet checked by restarting Grasshopper |
| core tests on Python 3.9; `uv version` + `uv build` give matching wheel versions | ✅ locally |
| `sync_yak_feed.py`, `setup_lab_pip.py` | ✅ `tests/test_clients.py` against a fake GitLab API |
| image builds with rootless BuildKit under the `image-build` runner's settings (seccomp/AppArmor unconfined, not privileged) | ✅ locally, same container settings |
| BuildKit's push to the GitLab registry | ❓ not yet: first run on the new runner |
| GitLab template | parses; **not yet run on git.rccn.dev** |
| generated `.ghuser` / `.yak` load in Rhino 8 | ✅ macOS, Rhino 8.37: `.yak` installed with `yak install`, vendored core imported from the package's `lib/`; ❌ Windows |
| Rhino's pip honours the user pip config (scenario C) | ❌ to verify on one machine |
| Rhino 8 accepts a folder as a package source; package install path (scenario D) | ❌ to verify on Windows and macOS |
| `registry.rccn.dev/libs/ghuser-builder:1.2.1` in `templates/local/*` | ❓ needs a lab login; check the `v1.2.1` release job |
| image built from the public mirror: `docker build -t ghuser-builder:1.2.1 https://github.com/rccn-dev/ghuser-builder.git#v1.2.1` | ✅ arm64 (macOS); ✅ amd64 (GitHub's ubuntu-latest, ghuser-template's CI, which builds and packages) |
