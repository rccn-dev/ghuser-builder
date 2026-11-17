# ghuser-builder

Build, verify and package **Grasshopper `.ghuser` components on Linux**, with no
Windows and no Rhino, in one Docker image that runs the same way on a laptop, in
GitLab CI and in GitHub Actions. Then ship them so many people can install and
update them from Rhino's Package Manager.

```
components/                         ghuser-build                    dist/
├── RingPoints/                     ─────────────►                  ├── ghuser/RingPoints.ghuser
│   ├── code.py                     1. componentize (GH_IO on Mono) └── my-tool-1.2.3-rh8_0-any.yak
│   ├── metadata.json               2. verify: read every file back
│   └── icon.png  (24×24)           3. package as .yak (optional)
```

It wraps the [COMPAS componentizer](https://github.com/compas-dev/compas-actions.ghpython_components)
(MIT, Gramazio Kohler Research). What this repo adds is the toolchain pinned in an
image, a verifier that fails the build if a `.ghuser` doesn't match its source,
`.yak` packaging without McNeel's Windows-only CLI, a GitLab CI template, and
deployment recipes for lab tools that are not on public PyPI.

**Rhino 8 script components (CPython) only.** The IronPython componentizer runs
only under IronPython on Windows; for Rhino 7 / GhPython use the upstream GitHub
Action on a Windows runner.

## Use it

Starting a project? [**ghuser-template**](https://github.com/rccn-dev/ghuser-template)
has the layout (core, tests, components), a linked dev loop and the `.yak` build, pinned
to a release of this repo.

### In a GitLab project (lab default)

```yaml
# .gitlab-ci.yml
include:
  - project: libs/ghuser-builder
    ref: v1.2.1
    file: templates/gitlab/ghuser.gitlab-ci.yml

variables:
  GHUSER_YAK_NAME: my-tool        # omit for .ghuser files only
```

Every pipeline builds and verifies; `dist/` is a downloadable artifact. Push a tag
`v1.2.3` to release: the `.yak` and `.ghuser` files go to the project's Package
Registry and a GitLab Release. Variables, jobs and how to override them are listed
at the top of [`templates/gitlab/ghuser.gitlab-ci.yml`](templates/gitlab/ghuser.gitlab-ci.yml).
To run the pipeline locally: [`gitlab-ci-local`](https://github.com/firecow/gitlab-ci-local).

### On your machine

```bash
docker build -t ghuser-builder:local https://github.com/rccn-dev/ghuser-builder.git#v1.2.1   # once
cp templates/local/ghuser <project>/scripts/ghuser
scripts/ghuser --yak my-tool               # components/ -> dist/
```

It runs `docker run` with the project folder mounted (on colima, start it with
`--mount-type virtiofs`: its default sshfs can serve a file you just saved in its old
version; ghuser-template's scripts avoid the mount altogether). On Windows, copy
`templates/local/ghuser.py` instead and run `uv run scripts/ghuser.py --yak my-tool`.
Either uses `ghuser-builder:local` unless `GHUSER_BUILDER_IMAGE` names another image. Where mounting is not possible
(`act` on macOS, some Docker-in-Docker setups), [`templates/local/Dockerfile`](templates/local/Dockerfile)
builds the same thing and exports it through BuildKit.

### Dev builds, linked into Grasshopper (macOS and Windows)

```bash
uv run <ghuser-builder>/local/ghuser_dev.py deploy components dist-dev --env src
uv run <ghuser-builder>/local/ghuser_dev.py build components dist-dev --env src   # build only
uv run <ghuser-builder>/local/ghuser_dev.py status dist-dev
uv run <ghuser-builder>/local/ghuser_dev.py uninstall dist-dev
```

`--env src` adds `# env: <abs path>` to each component: Rhino then imports your
core library straight from the working copy, so you edit and recompute without
reinstalling. A `# r: core=={{version}}` pin is left out of such a build, since
`--env` provides that library. Two builders:

- `--builder docker` (the default, every OS): `ghuser-build` in the image (`--image`, or
  `GHUSER_BUILDER_IMAGE`, default `ghuser-builder:local`), the one that builds releases.
  Full icons. The components go in and come back as a tar stream, not through a shared
  folder: colima's default sharing (sshfs) served a just-rewritten file in its old
  version in 1 of 8 tries, and a build must use what is on disk.
- `--builder rhino` (macOS, no Docker): the pinned componentizer on Rhino 8's own .NET
  and GH_IO. No canvas icon. For working on this repo.

What each edit needs, because Grasshopper reads each part at a different time:

| You edit | Read | Then |
| --- | --- | --- |
| the core (`--env`) | on every run | `deploy`: Rhino forgets it, the canvas recomputes |
| `code.py` | once, when a component is placed; saved in the `.gh` | replace the component |
| `metadata.json`, `icon.png`, a new component | when Grasshopper starts | restart Rhino, then replace |

`deploy` says this per component after each build. Every dev component also carries a
fingerprint of its `code.py`, `metadata.json` and `icon.png`, and checks it against
`dist-dev/ghuser-dev.json` when it compiles (placed, opened, reloaded). If the latest build
differs, or `uninstall` removed it, the component stops with the reason on the canvas
(`dev: replace`, `dev: restart, replace`, `dev: not deployed`) instead of running old code
quietly, including in a `.gh` file reopened later.

`deploy` builds, links `dist-dev` into Grasshopper's User Object folder as
`<folder>-dev` (`--name` to choose; a junction on Windows, no admin needed), and moves loose older copies of the same
components to `~/.cache/ghuser-builder/backups/`. It then checks the `# r:` requirements and the
components' imports in Rhino's own Python (`--requirements` installs what is
missing), and if Rhino is running, drops the core's modules (wherever they came from:
an installed `.yak` loads the same names), recompiles and recomputes the components
on the canvas, and names any that carry older code, which then stop
(`--no-reload` to skip). `status` says what Grasshopper will load and what collides,
including an installed package with the same components: uninstall it while you develop.

**Dev only:** no `.yak`, version `0.0.0-dev.local`, `# env:` paths that exist on one
machine. A vendored core (scenario D) needs a header that does not fail when no
package is installed; see [`examples/03`](examples/03-vendored-core). Releases always
come from CI, or `scripts/ghuser` with a version.

### In a GitHub project

[`templates/github/build-ghuser.yml`](templates/github/build-ghuser.yml): the same
image as a job `container:`. Mirror the image to ghcr.io first, or make the
registry public.

### `ghuser-build` options

| Option | Env | Default |
| --- | --- | --- |
| `--env PATH` | `GHUSER_ENV` | none: dev build importing the core from `PATH`; no `.yak` |
| `--version X.Y.Z` | `GHUSER_VERSION` | tag minus `v`; otherwise `0.0.0-dev.<pipeline>` |
| `--prefix TEXT` | `GHUSER_PREFIX` | none: prepended to every component name |
| `--yak NAME` | `GHUSER_YAK_NAME` | none: no `.yak` |
| `--yak-manifest FILE` | `GHUSER_YAK_MANIFEST` | `./yak.json` if present |
| `--yak-include SRC:DST` | `GHUSER_YAK_INCLUDE` | none: copy files into the package (scenario D) |

`{{version}}` anywhere in `code.py` becomes the release version. Use it to pin your
core library: `# r: my_core=={{version}}`. Dev versions (`0.0.0-dev.42`) are valid
both for Yak (semver) and for pip (PEP 440, read as `0.0.0.dev42`).

## Shipping it: which scenario?

| Your tool | Core library goes to | Users install | Details |
| --- | --- | --- | --- |
| **A.** components only, no library | | the `.yak` | [A](docs/deploy-scenarios.md#a-components-only) |
| **B.** open source | pypi.org | `.yak` from McNeel's public server | [B](docs/deploy-scenarios.md#b-open-source-public-pypi--public-yak) |
| **C.** lab tool, lab GitLab available | the lab GitLab's PyPI registry | `.yak` from a shared folder; pip set up once | [C](docs/deploy-scenarios.md#c-lab-tool-private-registry-on-the-lab-gitlab) |
| **D.** lab tool, nothing to configure | inside the `.yak` | the `.yak` | [D](docs/deploy-scenarios.md#d-lab-tool-core-vendored-into-the-yak) |
| **E.** quick, one studio | | a synced folder | [E](docs/deploy-scenarios.md#e-a-synced-userobjects-folder) |

Short version: **open source → B. Lab tool → D** if the core is pure Python and has
no private dependencies, **C** once several tools share libraries. Use **E** only
for throwaway tools.

## Examples

| | Scenario | Shows |
| --- | --- | --- |
| [`examples/01-standalone`](examples/01-standalone) | A | a component that needs nothing but Rhino |
| [`examples/02-with-core`](examples/02-with-core) | C (and B) | a tested core library (`ringkit`) + a thin adapter pinned with `# r: ringkit=={{version}}` |
| [`examples/03-vendored-core`](examples/03-vendored-core) | D | the same core shipped inside the `.yak`, found via `sys.path` |

`tests/run_examples.sh` builds all three inside the image and checks the output,
including that the verifier really fails when it should.

## What is pinned, and releasing

The image tag names one exact toolchain, recorded as image labels:

| Pin | Why | Where |
| --- | --- | --- |
| `GH_VERSION` (GH_IO.dll) | a `.ghuser` written by a newer GH_IO than the user's Rhino won't load | `Dockerfile` |
| `COMPONENTIZER_SHA` | the file format the componentizer writes | `Dockerfile` |
| `pythonnet` | hosts Mono from Python | `Dockerfile` |
| base image digest | reproducible builds; CI's layer cache stays valid until you bump it | `Dockerfile` `FROM` |

To release a new image: bump a pin, set the template's `GHUSER_BUILDER_IMAGE` to the
new version, then tag `vX.Y.Z`. CI builds the image with BuildKit, tests it on the
examples, and copies exactly the tested image to `$CI_REGISTRY_IMAGE:X.Y.Z` with
crane. CI refuses a tag that doesn't match the template.

### Runner for image builds

Only the `image:build` job needs more than an ordinary runner: one extra runner,
tagged `image-build`, with seccomp/AppArmor relaxed (not privileged). Step-by-step
setup and troubleshooting: **[docs/runner-setup.md](docs/runner-setup.md)**.

Projects upgrade by changing `ref:` in their `include:`: the template and image
move together.

## Status: what has been checked

How to check, and what to run before a release: [`docs/validation.md`](docs/validation.md).
The dev-loop scenarios run headless and in Docker on every push, and in Rhino by hand.

| Claim | Checked |
| --- | --- |
| dev-loop scenarios (`tests/scenarios.py`: core, `code.py`, metadata, icon, added, removed, renamed, moved, upgraded, uninstalled) | ✅ headless (`tests/test_dev_scenarios.py`); ✅ Docker, arm64 (colima); ✅ Rhino 8.37, macOS (`tests/rhino/run_scenarios.py`), 2026-11-17; ❓ Windows; ❓ amd64 Docker until the GitHub `tests` workflow runs |
| a component whose top level fails (its `src/` gone) keeps its `dev:` label | ✅ Rhino 8.37, macOS |
| image builds (arm64, Docker 27); examples build, verify and package | ✅ `tests/run_examples.sh` |
| verifier rejects a mismatched `.ghuser`, and one without a canvas icon | ✅ same script |
| `local/ghuser_dev.py` with Rhino 8.36 (.NET 10) on macOS (arm64) | ✅ example 02 with `--env src` |
| `ghuser_dev.py deploy` reload: drops `--env` modules, recompiles, recomputes, flags stale canvas code | ✅ example 02 in Rhino 8.36; a core imported at the top of `code.py`, with typed inputs, in Rhino 8.37 |
| reload drops a core of the same name left by an installed `.yak` | ✅ Rhino 8.37, macOS |
| `ghuser_dev.py --builder docker` (tar stream) and `ghuser-build --env` | ✅ macOS, colima with sshfs (5 quick size-changing edits, all verified); `tests/run_examples.sh` |
| `ghuser_dev.py` link, backup, status, uninstall | ✅ `tests/test_ghuser_dev.py` (symlinks) |
| `ghuser_dev.py` on Windows: junction, `%APPDATA%` paths, `rhinocode.exe`, Rhino's Python | ✅ lab PC, 1.1.0 (ghuser-template's dev loop); ❓ 1.2.0's stale check and tar stream |
| `templates/local/ghuser.py` | ✅ macOS; ❌ Windows |
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
