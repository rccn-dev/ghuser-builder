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

```bash
docker build -t ghuser-builder:local https://github.com/rccn-dev/ghuser-builder.git#v1.2.1   # once
cp templates/local/ghuser <project>/scripts/ghuser
scripts/ghuser --yak my-tool               # components/ -> dist/
```

It runs `docker run` with the project folder mounted. On colima, start it with
`--mount-type virtiofs`: its default sshfs can serve a file you just saved in its old
version (ghuser-template's scripts avoid the mount altogether, sending files as a tar
stream). On Windows, copy `templates/local/ghuser.py` instead and run
`uv run scripts/ghuser.py --yak my-tool`. Either uses `ghuser-builder:local` unless
`GHUSER_BUILDER_IMAGE` names another image.

Where mounting is not possible (`act` on macOS, some Docker-in-Docker setups),
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

[`templates/github/build-ghuser.yml`](../templates/github/build-ghuser.yml): the same image
as a job `container:`. Mirror the image to ghcr.io first, or make the registry public.
ghuser-template does it differently: it builds the image on the runner from the pinned
release, with the same script as on a laptop.
