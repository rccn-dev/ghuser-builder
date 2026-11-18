# ghuser-builder

Turns a folder of Grasshopper Python components into `.ghuser` files and a Rhino
package (`.yak`) that anyone installs from Rhino's Package Manager. The build runs in
Docker, so it needs no Windows and no Rhino. Rhino 8 script components (CPython) only.

## Start here

Starting a new tool? Make it from **[ghuser-template](https://github.com/rccn-dev/ghuser-template)**
("Use this template"). Everything below is already wired up there:

```bash
uv run scripts/dev.py                       # try the components in Grasshopper
uv run scripts/ghuser.py --version 0.1.0    # make the .yak
```

## You need

- **Docker**, running: Docker Desktop, OrbStack or colima
- **[uv](https://docs.astral.sh/uv/)**
- **Rhino 8**, only to try the components (building does not need it)

## Your components

One folder per component, under `components/`:

```
components/RingPoints/
├── code.py          the component's Python
├── metadata.json    name, category, inputs, outputs
└── icon.png         24 × 24
```

## Not made from the template?

Copy ghuser-template's `scripts/` folder and the `[tool.ghuser]` table of its
`pyproject.toml` into your project, set `yak-name` (and `yak-include` if the core ships
inside), and use the two commands above. They build the pinned image on first use and
send files to Docker as a tar stream, so every Docker builds what is on disk.

Underneath, `scripts/dev.py` runs [`local/ghuser_dev.py`](local/ghuser_dev.py) at the
pinned release, and `scripts/ghuser.py` runs `ghuser-build` in the image. Their options:
[usage.md](docs/usage.md); how the dev loop works and what each edit needs:
[dev-builds.md](docs/dev-builds.md).

## Build in CI

- **GitLab:** include the template; every push builds, a tag `v1.2.3` releases.
  ```yaml
  include:
    - project: libs/ghuser-builder
      ref: v1.2.1
      file: templates/gitlab/ghuser.gitlab-ci.yml
  variables:
    GHUSER_YAK_NAME: my-tool
  ```
- **GitHub:** ghuser-template's `.github/workflows/`: it builds the pinned image on
  the runner with the same `scripts/ghuser.py` as on a laptop.

## When something goes wrong

| You see | Do |
| --- | --- |
| `docker not found`, or Docker is not running | install or start Docker; the message says how |
| `[FAILED] <component>: ...` | fix what it names in that folder; nothing was written |
| a component twice in Grasshopper | `uv run scripts/dev.py status` names the copy; uninstall the package while you develop |
| a red component labelled `dev: ...` | replace it; restart Rhino first if the label says so ([what each means](docs/dev-builds.md#stale-components-stop)) |
| the core imports an old version | `uv run scripts/dev.py` again with Rhino open; or restart Rhino |

## More

- [Every option, local runners, CI templates](docs/usage.md)
- [How dev builds work](docs/dev-builds.md)
- [Shipping a tool that has its own library: five scenarios](docs/deploy-scenarios.md)
- [Testing, the release checklist, and what has been checked](docs/validation.md)
- [Pins, releasing this image, the CI runner, examples](docs/maintaining.md)
