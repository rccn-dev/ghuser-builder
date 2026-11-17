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

## Make the .yak

From your project folder:

```bash
docker build -t ghuser-builder:local https://github.com/rccn-dev/ghuser-builder.git#v1.2.1   # once
cp <ghuser-builder>/templates/local/ghuser scripts/ghuser          # once (Windows: ghuser.py)
scripts/ghuser --yak my-tool --version 0.1.0                      # -> dist/my-tool-0.1.0-rh8_0-any.yak
```

Drag the `.yak` onto Rhino 8 and restart Rhino.

## Try components while you work

```bash
uv run <ghuser-builder>/local/ghuser_dev.py deploy components dist-dev --env src
```

The components appear in Grasshopper (after a first restart) and read your core
library straight from `src/`. Run the same command after every edit, then:

| You edited | Do |
| --- | --- |
| the core in `src/` | nothing: the canvas updates |
| a `code.py` | replace that component on the canvas |
| a `metadata.json` or `icon.png`, or added a component | restart Rhino, then replace it |

A component that needs replacing turns red and says so (`dev: replace`). Before you
install the `.yak`, remove the dev link:
`uv run <ghuser-builder>/local/ghuser_dev.py uninstall dist-dev`.

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
- **GitHub:** use ghuser-template's workflows, or copy
  [`templates/github/build-ghuser.yml`](templates/github/build-ghuser.yml).

## When something goes wrong

| You see | Do |
| --- | --- |
| `docker not found`, or Docker is not running | install or start Docker; the message says how |
| `[FAILED] <component>: ...` | fix what it names in that folder; nothing was written |
| a component twice in Grasshopper | `ghuser_dev.py status dist-dev` names the copy; uninstall the package while you develop |
| a red component labelled `dev: ...` | replace it; restart Rhino first if the label says so |
| the core imports an old version | `deploy` again with Rhino open; or restart Rhino |

## More

- [Every option, local runners, CI templates](docs/usage.md)
- [How dev builds work](docs/dev-builds.md)
- [Shipping a tool that has its own library: five scenarios](docs/deploy-scenarios.md)
- [Testing, the release checklist, and what has been checked](docs/validation.md)
- [Pins, releasing this image, the CI runner, examples](docs/maintaining.md)
