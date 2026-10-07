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

### In a GitLab project (lab default)

```yaml
# .gitlab-ci.yml
include:
  - project: libs/ghuser-builder
    ref: v1.0.0
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
cp templates/local/ghuser <project>/scripts/ghuser
scripts/ghuser --yak my-tool               # components/ -> dist/
```

It runs `docker run` with the project folder mounted. Where mounting is not possible
(`act` on macOS, some Docker-in-Docker setups), [`templates/local/Dockerfile`](templates/local/Dockerfile)
builds the same thing and exports it through BuildKit.

### In a GitHub project

[`templates/github/build-ghuser.yml`](templates/github/build-ghuser.yml): the same
image as a job `container:`. Mirror the image to ghcr.io first, or make the
registry public.

### `ghuser-build` options

| Option | Env | Default |
| --- | --- | --- |
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

To release a new image: bump a pin, set the template's `GHUSER_BUILDER_IMAGE` to the
new version, then tag `vX.Y.Z`. CI builds, tests on the examples, and pushes
`$CI_REGISTRY_IMAGE:X.Y.Z`. CI refuses a tag that doesn't match the template. The
build job needs a **privileged runner** (Docker-in-Docker). Without one, build on a
lab machine with `docker build -t <registry>/libs/ghuser-builder:X.Y.Z . && docker push …`.

Projects upgrade by changing `ref:` in their `include:`: the template and image
move together.

## Status: what has been checked

| Claim | Checked |
| --- | --- |
| image builds (arm64, Docker 27); examples build, verify and package | ✅ `tests/run_examples.sh` |
| verifier rejects a mismatched `.ghuser` | ✅ same script |
| core tests on Python 3.9; `uv version` + `uv build` give matching wheel versions | ✅ locally |
| `sync_yak_feed.py`, `setup_lab_pip.py` | ✅ `tests/test_clients.py` against a fake GitLab API |
| GitLab template | parses; **not yet run on git.rccn.dev** |
| generated `.ghuser` / `.yak` load in Rhino 8 | ❌ **not yet tested in Rhino.** Do this before relying on it |
| Rhino's pip honours the user pip config (scenario C) | ❌ to verify on one machine |
| Rhino 8 accepts a folder as a package source; package install path (scenario D) | ❌ to verify on Windows and macOS |
| registry host `git.rccn.dev:5050` in `templates/local/*` | ❓ placeholder: replace with the lab's registry address |
