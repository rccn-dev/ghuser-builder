# Building: options, runners and CI

The [README](../README.md) has the short version. This page has every option.

## What it does

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
`.yak` packaging without McNeel's Windows-only CLI, CI templates, a linked dev loop
([dev-builds.md](dev-builds.md)), and deployment recipes for lab tools that are not on
public PyPI ([deploy-scenarios.md](deploy-scenarios.md)).

**Rhino 8 script components (CPython) only.** The IronPython componentizer runs only
under IronPython on Windows; for Rhino 7 / GhPython use the upstream GitHub Action on a
Windows runner.

## `ghuser-build` options

The command inside the image. Each option can also be set by an environment variable.

| Option | Env | Default |
| --- | --- | --- |
| `--version X.Y.Z` | `GHUSER_VERSION` | tag minus `v`; otherwise `0.0.0-dev.<pipeline>` |
| `--prefix TEXT` | `GHUSER_PREFIX` | none: prepended to every component name |
| `--yak NAME` | `GHUSER_YAK_NAME` | none: no `.yak` |
| `--yak-manifest FILE` | `GHUSER_YAK_MANIFEST` | `./yak.json` if present |
| `--yak-include SRC:DST` | `GHUSER_YAK_INCLUDE` | none: copy files into the package (scenario D) |
| `--env PATH` | `GHUSER_ENV` | none: dev build importing the core from `PATH`; no `.yak` |

`{{version}}` anywhere in `code.py` becomes the release version. Use it to pin your
core library: `# r: my_core=={{version}}`. Dev versions (`0.0.0-dev.42`) are valid both
for Yak (semver) and for pip (PEP 440, read as `0.0.0.dev42`).

Output: `<out>/ghuser/*.ghuser`, plus `<out>/*.yak` with `--yak`. Nothing is half-written
when packaging or verification fails.

## On your machine

Use ghuser-template's `scripts/ghuser.py` (any OS): it reads `[tool.ghuser]` from
`pyproject.toml`, builds `ghuser-builder:<release>` from the pinned tag the first time,
and sends the components to the container as a tar stream, never a mounted folder.
Options after it pass through to `ghuser-build`. `GHUSER_BUILDER_IMAGE` names another
image; `GHUSER_BUILDER_SRC=<checkout>` builds from a checkout (testing a branch).

[`templates/local/`](../templates/local) holds the older scripts that mount the project
folder (`ghuser`, `ghuser.py`): superseded, and removed in 1.3.0. A mount on colima's
default sshfs can serve a file you just saved in its old version. Where neither a mount
nor stdin works (`act` on macOS, some Docker-in-Docker setups),
[`templates/local/Dockerfile`](../templates/local/Dockerfile) builds the same thing and
exports it through BuildKit.

## In a GitLab project (lab default)

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
`v1.2.3` to release: the `.yak` and `.ghuser` files go to the project's Package Registry
and a GitLab Release. Variables, jobs and how to override them are listed at the top of
[`templates/gitlab/ghuser.gitlab-ci.yml`](../templates/gitlab/ghuser.gitlab-ci.yml). To run
the pipeline locally: [`gitlab-ci-local`](https://github.com/firecow/gitlab-ci-local).

Projects upgrade by changing `ref:` in their `include:`: the template and image move together.

## In a GitHub project

Use ghuser-template's `.github/workflows/build-ghuser.yml`: it runs `scripts/ghuser.py`
on the runner, which builds the image from the pinned release, so nothing needs to be
published to a registry. [`templates/github/build-ghuser.yml`](../templates/github/build-ghuser.yml)
runs a mirrored image as a job `container:`; no such mirror is published, so it is
superseded and removed in 1.3.0.
