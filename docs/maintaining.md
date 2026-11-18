# Maintaining ghuser-builder

## What is pinned

The image tag names one exact toolchain, recorded as image labels:

| Pin | Why | Where |
| --- | --- | --- |
| `GH_VERSION` (GH_IO.dll) | a `.ghuser` written by a newer GH_IO than the user's Rhino won't load | `Dockerfile` |
| `COMPONENTIZER_SHA` | the file format the componentizer writes | `Dockerfile` |
| `pythonnet` | hosts Mono from Python | `Dockerfile` |
| base image digest | reproducible builds; CI's layer cache stays valid until you bump it | `Dockerfile` `FROM` |

## Releasing

1. Bump a pin, or change the tools.
2. Set every `1.x.y` in `templates/`, `README.md` and `docs/usage.md` to the new version.
3. Run the release checks in [validation.md](validation.md).
4. Tag `vX.Y.Z` and push to `origin` (it pushes to GitLab and the GitHub mirror).

GitLab CI builds the image with BuildKit, tests it on the examples, and copies exactly
the tested image to `$CI_REGISTRY_IMAGE:X.Y.Z` with crane. It refuses a tag that doesn't
match `templates/gitlab/ghuser.gitlab-ci.yml`. Then bump `[tool.ghuser] builder` in
ghuser-template (and in projects made from it, on purpose).

## Planned for 1.3.0

After the 2026-11-18 class (moving the pin then makes every lab PC rebuild the image):

- **One local client, here.** The tar-stream run, `IN_IMAGE`, and telling Docker Desktop,
  colima and OrbStack apart move from ghuser-template's `scripts/_builder.py` into
  `local/`, used by both `ghuser_dev.py` and a release build. The template's scripts shrink
  to: read `[tool.ghuser]`, fetch the pinned release, hand over.
- **The component checks fail the build.** `RunScript` names the inputs in
  `metadata.json` and returns one value per output; `typeHintID`, `scriptParamAccess` and
  `exposure` take values the componentizer accepts (read from it, not copied); the adapter
  imports `Grasshopper`, `Rhino` and `System`; the icon is 24 × 24. They now live in the
  template's `tests/test_components.py`, so only projects that copied it get them; the
  template keeps the checks that are its own (class name = folder, `PACKAGE` = `yak-name`).
- **Removed:** `templates/local/ghuser`, `templates/local/ghuser.py`,
  `templates/github/build-ghuser.yml`.
- Then ghuser-template, `plugin_set` and projects made from the template move to 1.3.0.

## Runner for image builds

Only the `image:build` job needs more than an ordinary runner: one extra runner, tagged
`image-build`, with seccomp/AppArmor relaxed (not privileged). Setup and troubleshooting:
[runner-setup.md](runner-setup.md).

## Examples

| | Scenario | Shows |
| --- | --- | --- |
| [`examples/01-standalone`](../examples/01-standalone) | A | a component that needs nothing but Rhino |
| [`examples/02-with-core`](../examples/02-with-core) | C (and B) | a tested core library (`ringkit`) + a thin adapter pinned with `# r: ringkit=={{version}}` |
| [`examples/03-vendored-core`](../examples/03-vendored-core) | D | the same core shipped inside the `.yak`, found via `sys.path` |

## Tests

| What | Command |
| --- | --- |
| examples build, verify and package; the verifier fails when it should | `docker run --rm -v "$PWD:/repo" -w /repo <image> tests/run_examples.sh` |
| tools, links, clients, dev-loop scenarios (headless) | `uv run --no-project --with pytest pytest tests` |
| the scenarios built in Docker | `GHUSER_TEST_IMAGE=<image> uv run --no-project --with pytest pytest tests/test_dev_scenarios.py` |
| the scenarios in a running Rhino | `uv run tests/rhino/run_scenarios.py --image <image>` |

GitLab runs the first two; the GitHub mirror runs the second on Linux, macOS and Windows
and the third on amd64. Levels, scenarios and the manual checklist: [validation.md](validation.md).
