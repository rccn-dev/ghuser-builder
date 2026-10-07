# Deploying Grasshopper components: five scenarios

What users need on their machine depends on one question: **does the component's
`code.py` import a library of yours?** A `.ghuser` file carries only the component's
own code. Any library it imports has to reach the user's Rhino some other way, and at
the version the component was built against. Each scenario is one answer to "some
other way".

| | Library reaches users via | User setup, once | Update path | Needs |
| --- | --- | --- | --- | --- |
| **A** | (no library) | add package source | Package Manager | |
| **B** | pypi.org (`# r:` line) | none | Package Manager | public code |
| **C** | lab GitLab PyPI registry (`# r:` line) | pip config + package source | Package Manager | lab GitLab, network |
| **D** | inside the `.yak` | add package source | Package Manager | pure-Python core |
| **E** | (no library) | point at a synced folder | automatic, no versions | a sync tool |

Two rules hold in every scenario:

- **One version number for everything.** Tag `v1.2.3` → components built with
  `{{version}}` = `1.2.3` → library `1.2.3` → `my-tool-1.2.3-rh8_0-any.yak`.
  Components pin `# r: my_core=={{version}}`, so a component never meets a library it
  wasn't built against.
- **Test the core where it runs.** Rhino 8 embeds CPython **3.9**; the template's
  `core:test` job runs your tests under 3.9.

---

## A. Components only

The component needs nothing but Rhino (and maybe public packages via `# r: compas`).
Example: [`examples/01-standalone`](../examples/01-standalone).

**Publisher:** include the template, set `GHUSER_YAK_NAME`, push a tag. The `.yak`
lands in the project's Package Registry and a Release.

**Users:** install the `.yak` the way the lab distributes it: a shared folder (see C,
"the package feed") or McNeel's public server (B).

---

## B. Open source: public PyPI + public Yak

**Publisher:**

1. `GHUSER_CORE_DIR: "."` and `GHUSER_PYPI: pypi`, plus a masked, protected CI/CD
   variable `PYPI_TOKEN` (a PyPI token scoped to this one project).
2. Components declare `# r: my_core=={{version}}`.
3. To also publish the `.yak` to `yak.rhino3d.com`: the `yak` CLI ships only for
   Windows and macOS, so add a job on a Windows runner:

   ```yaml
   yak:push:
     extends: .ghuser:yak-push
     tags: [windows]
   ```

   with a masked `YAK_TOKEN` (from `yak login --ci`, per McNeel's docs). Without a
   Windows runner, download the `.yak` from the Release and `yak push` it by hand.
   The first push of a package name claims it on the public server.

**Users:** Rhino 8 → `PackageManager` → search → Install. The first time a component
runs, Rhino installs `my_core` from pypi.org because of the `# r:` line.

---

## C. Lab tool: private registry on the lab GitLab

The core library stays on `git.rccn.dev`, not on pypi.org. Example:
[`examples/02-with-core`](../examples/02-with-core).

**Publisher:**

```yaml
variables:
  GHUSER_YAK_NAME: rccn-ringkit
  GHUSER_CORE_DIR: "."
  GHUSER_PYPI: gitlab        # wheel -> this project's PyPI-compatible registry
```

Put lab tool projects in **one GitLab group**, so users configure one index for
all of them: `https://git.rccn.dev/api/v4/groups/<group-id>/-/packages/pypi/simple`.

**Users, once per machine:**

1. **pip → lab registry.** Run with any Python (Rhino 8's own works):

   ```bash
   python clients/setup_lab_pip.py --gitlab https://git.rccn.dev --group-id <id>
   ```

   It sets pip's `index-url` (not `extra-index-url`) to the group endpoint. GitLab
   forwards names it doesn't host (e.g. `compas`) to pypi.org, and a look-alike package
   on pypi.org can't shadow a lab package. That relies on the instance setting
   *Forward PyPI package requests*, which is on by default.

   If the group is **not public**, add `--token`, using a **group deploy token** with
   only `read_package_registry`. It ends up in a plain-text file on every lab
   machine, so never use a personal token, and rotate it each semester.

   ⚠️ To verify once: that the pip inside Rhino 8 reads this user config when it
   processes `# r:` lines. If it doesn't, set the environment variable
   `PIP_INDEX_URL` system-wide instead (same URL), or use scenario D.

2. **The package feed.** Rhino's Package Manager installs from package *sources*;
   GitLab's registry is not one. So mirror releases into a folder:

   ```bash
   python clients/sync_yak_feed.py --gitlab https://git.rccn.dev \
       --project rccn/ringkit --package rccn-ringkit --dest "//lab-nas/rhino-packages"
   ```

   Run it on a schedule on **one** machine that can write the lab's shared folder
   (NAS, or a OneDrive/Syncthing folder). Then each user adds that folder as an extra
   package source in Rhino 8 (Options → Package Manager → Sources, or the advanced
   setting `Rhino.Options.PackageManager.Sources`).

   ⚠️ To verify once on Windows and macOS: that a plain folder of `.yak` files works
   as a source in your Rhino version. Fallback that needs no source at all: download
   the `.yak` from the GitLab Release and drag it onto Rhino, or install it with
   the `yak` CLI that ships with Rhino.

**Update:** tag a new version → the feed picks it up → users see the update in the
Package Manager → the new components pin the new library → pip fetches it on first run.
**Rollback:** reinstall the previous version from the Package Manager; its components
still pin the older library, which is still in the registry.

---

## D. Lab tool: core vendored into the `.yak`

No registry and no pip configuration: the library travels inside the package.
Example: [`examples/03-vendored-core`](../examples/03-vendored-core).

**Publisher:**

```yaml
variables:
  GHUSER_YAK_NAME: rccn-ringkit-vendored
  GHUSER_YAK_INCLUDE: "src/ringkit:lib/ringkit"     # SRC:DST inside the .yak
```

Each component starts with a short bootstrap (see the example's `code.py`). It finds
`<packages>/<rhino>/<name>/{{version}}/lib` and puts it on `sys.path`, so every
component loads the core from its own package version.

**Users:** install the `.yak` (feed folder as in C, or drag and drop). Nothing else.

**Limits.** Pure-Python cores only: a compiled extension would need one build per
OS and Python. Public dependencies still come from `# r:` lines. And Python caches
imported modules, so after updating a package, **restart Rhino**: otherwise the old
core stays loaded.

⚠️ To verify once: the package install folder the bootstrap searches,
`%APPDATA%\McNeel\Rhinoceros\packages\<ver>\` on Windows and
`~/Library/Application Support/McNeel/Rhinoceros/packages/<ver>/` on macOS.

---

## E. A synced UserObjects folder

Grasshopper loads every `.ghuser` in its UserObjects folder (`File → Special
Folders → User Object Folder`). Point a OneDrive or Syncthing folder there, or link one
into it, and drop the CI artifact's `dist/ghuser/*.ghuser` in.

Zero infrastructure, but **no versions, no rollback, and no way to deliver a
library.** Everyone gets whatever was last copied in. Use it for one studio's
short-lived tools, not for anything others build on.

---

## Before relying on any of this

1. Load one `.ghuser` from each example in Rhino 8 on Windows and on macOS.
2. Install one `.yak` from a folder source.
3. For C: confirm Rhino's pip uses the lab index (watch the `# r:` install in the
   script editor's console).

Then update the "Status" table in the README.
