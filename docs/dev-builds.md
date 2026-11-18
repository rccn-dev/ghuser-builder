# Dev builds, linked into Grasshopper

`local/ghuser_dev.py` builds components for one machine and links them into
Grasshopper, so you edit and recompute without installing anything. macOS and
Windows, Rhino 8. The [README](../README.md) has the commands; this page says how it works.

```bash
uv run <ghuser-builder>/local/ghuser_dev.py deploy components dist-dev --env src
uv run <ghuser-builder>/local/ghuser_dev.py build components dist-dev --env src   # build only
uv run <ghuser-builder>/local/ghuser_dev.py status dist-dev
uv run <ghuser-builder>/local/ghuser_dev.py uninstall dist-dev
```

In a project made from ghuser-template, `uv run scripts/dev.py [status|uninstall]` runs
these at the pinned release.

## The core, read from your working copy

`--env src` adds `# env: <abs path>` to each component: Rhino then imports your core
library straight from `src/`. A `# r: core=={{version}}` pin is left out of such a build,
since `--env` provides that library.

A vendored core (scenario D) needs a header that does not fail when no package is
installed; see [`examples/03`](../examples/03-vendored-core).

## Builders

- `--builder docker` (the default, every OS): `ghuser-build` in the image (`--image`, or
  `GHUSER_BUILDER_IMAGE`, default `ghuser-builder:local`), the one that builds releases.
  Full icons. The components go in and come back as a tar stream, not through a shared
  folder: colima's default sharing (sshfs) served a just-rewritten file in its old version
  in 1 of 8 tries, and a build must use what is on disk.
- `--builder rhino` (macOS, no Docker): the pinned componentizer on Rhino 8's own .NET and
  GH_IO. No canvas icon. For working on this repo.

## What `deploy` does

1. Builds into `dist-dev/` (replacing what was there) and writes `dist-dev/ghuser-dev.json`,
   the fingerprints of this build.
2. Links `dist-dev` into Grasshopper's User Object folder as `<folder>-dev` (`--name` to
   choose): a symlink on macOS, a junction on Windows (no admin needed). Loose older copies
   of the same components move to `~/.cache/ghuser-builder/backups/`.
3. Checks the `# r:` requirements and the components' imports in Rhino's own Python
   (`--requirements` installs what is missing).
4. If Rhino is running (`--no-reload` to skip), through `rhinocode`:
   - drops the core's modules, wherever they came from (an installed `.yak` loads the same names);
   - recompiles and recomputes the components of this build on the canvas;
   - names any that carry older code, which then stop.
5. Says, per component, what changed and what to do.

`status` says what Grasshopper will load and what collides, including an installed
package with the same components: uninstall it while you develop. `uninstall` removes the
link and the fingerprints, so dev components still on a canvas stop (at once in a running Rhino).

## Why some edits need more than `deploy`

Grasshopper reads each part at a different time:

| You edit | Grasshopper reads it | Then |
| --- | --- | --- |
| the core (`--env`) | on every run | `deploy`: Rhino forgets it, the canvas recomputes |
| `code.py` | once, when a component is placed; saved in the `.gh` | replace the component |
| `metadata.json`, `icon.png`, a new component | when Grasshopper starts | restart Rhino, then replace |

## Stale components stop

A placed component keeps the `code.py` it was placed with, and a `.gh` file saves it that
way. So every dev component carries a fingerprint of its `code.py` (with the `# env:` path),
`metadata.json` and `icon.png`, and checks it against `dist-dev/ghuser-dev.json` when it
compiles: when placed, when a file is opened, when `deploy` reloads. If the latest build
differs, the component stops with the reason on the canvas instead of running old code:

| Label | Means | Do |
| --- | --- | --- |
| `dev: replace` | `code.py` changed (or the project moved, or ghuser-builder changed) | replace it from the toolbar |
| `dev: restart, replace` | inputs, outputs or icon changed | restart Rhino, then replace it |
| `dev: removed` | the component is no longer in the build | delete it |
| `dev: not deployed` | `uninstall` ran, or the project is gone | replace it from the installed package |

The label is set first; the full reason shows as the component's error. When the top of
`code.py` fails before that (its `src/` is gone), Rhino shows its own error, with the label.
Release builds carry none of this.

## Dev only

No `.yak`, version `0.0.0-dev.local`, `# env:` paths that exist on one machine.
Releases always come from CI, or `ghuser-build` with a version.

What each scenario must do, and how it is tested: [validation.md](validation.md).
