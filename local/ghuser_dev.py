# /// script
# requires-python = ">=3.10,<3.14"   # pythonnet 3.0.5 supports up to 3.13
# dependencies = ["pythonnet==3.0.5"]
# ///
"""Development builds of .ghuser components, linked into Grasshopper on this machine.

    uv run <ghuser-builder>/local/ghuser_dev.py build components dist-dev [--env src]
    uv run <ghuser-builder>/local/ghuser_dev.py deploy components dist-dev [--env src]
    uv run <ghuser-builder>/local/ghuser_dev.py status dist-dev
    uv run <ghuser-builder>/local/ghuser_dev.py uninstall dist-dev

macOS and Windows, Rhino 8. Two builders (--builder):
  docker  the default, on every OS: ghuser-build in the builder image (--image, or
          GHUSER_BUILDER_IMAGE), the same one that builds a release. Full icons.
          The components go in and come back as a tar stream, not a shared folder,
          whose cache (colima's sshfs) can hand Docker a file in its old version.
  rhino   macOS only, no Docker: the same pinned componentizer on Rhino 8's own
          .NET and GH_IO.dll. No canvas icon. For working on ghuser-builder itself.
`ghuser_dev.py components dist-dev` (no command) is `build`, as before.

build      componentize and verify into OUT, replacing what was there.
deploy     build, then link OUT into Grasshopper's User Object folder as NAME
           (default: <current folder>-dev; a junction on Windows). Loose copies of the same components
           elsewhere in that folder move to ~/.cache/ghuser-builder/backups/<time>/, so
           Grasshopper loads one of each. Then checks, in Rhino's own Python, the
           `# r:` requirements and that what the components import imports; with
           Rhino running, drops modules loaded from --env and recomputes the
           components on the canvas. Says, per component, what changed and what
           to do: replace it on the canvas, or restart Rhino first.
             --requirements  install missing `# r:` packages into Rhino, visibly
             --no-reload     leave a running Rhino alone
status     where OUT is linked, and anything that will go wrong when it loads,
           including an installed package carrying the same components.
uninstall  remove the links to OUT and its stamps file, so components placed from
           it stop. Backups stay where deploy put them.

--env PATH   prepends `# env: <absolute PATH>` to every component, so Rhino imports
             your core library straight from the working copy. Edit, recompute,
             no reinstall. (The idea comes from the ChiaChing-Yen fork of the
             compas componentizer.) A `# r:` pin on {{version}} names that same
             library, so a dev build with --env leaves it out: 0.0.0-dev.local
             is on no index.

STALE COMPONENTS. A component on the canvas keeps the code.py it was placed with,
and it is saved in the .gh file like that. Every dev component carries a fingerprint of its
code.py, metadata.json and icon.png, and stops with an error when OUT/ghuser-dev.json
(written by each build) says the latest build differs, or is gone. So an old
component in a reopened file is never run quietly.

DEV ONLY, by design:
  * with the rhino builder, no canvas icon: Rhino's macOS System.Drawing cannot
    create a bitmap outside a running Rhino, so components show the default script
    icon on the canvas (the toolbar icon is unaffected);
  * no .yak, and the version is always 0.0.0-dev.local;
  * `# env:` paths only exist on this machine.
Releases come from CI (ghuser-build in the Linux image), which has full icons.

GHUSER_USEROBJECTS, GHUSER_PACKAGES and GHUSER_BACKUPS override the User Object,
installed-package and backup folders (tests use them).
"""

import argparse
import ast
import io
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
sys.path.insert(0, TOOLS)
import dev_code as staging  # noqa: E402
from dev_code import bundles, dev_code, env_header, split_requirements  # noqa: E402

WINDOWS = platform.system() == "Windows"
RHINO = "/Applications/Rhino 8.app/Contents/Frameworks/RhCore.framework/Versions/A/Resources"
RHINO_PYTHON = os.path.expanduser("~/.rhinocode/py39-rh8")  # the same place on Windows
if WINDOWS:
    _APPDATA = os.environ.get("APPDATA", os.path.expanduser("~/AppData/Roaming"))
    _PROGRAMS = os.environ.get("ProgramFiles", r"C:\Program Files")
    RHINOCODE = os.path.join(_PROGRAMS, "Rhino 8", "System", "rhinocode.exe")
    PYTHON_EXE = "python.exe"
    USER_OBJECTS = os.path.join(_APPDATA, "Grasshopper", "UserObjects")
    PACKAGES = os.path.join(_APPDATA, "McNeel", "Rhinoceros", "packages", "8.0")
else:
    RHINOCODE = "/Applications/Rhino 8.app/Contents/Resources/bin/rhinocode"
    PYTHON_EXE = "python3.9"
    USER_OBJECTS = os.path.expanduser(
        "~/Library/Application Support/McNeel/Rhinoceros/8.0/Plug-ins/"
        "Grasshopper (b45a29b1-4343-4035-989e-044e8580d9cf)/UserObjects"
    )
    PACKAGES = os.path.expanduser("~/Library/Application Support/McNeel/Rhinoceros/packages/8.0")
IMAGE = "ghuser-builder:local"
VERSION = "0.0.0-dev.local"
STAMPS = "ghuser-dev.json"
# In the container: unpack stdin into a fresh folder, run the command, send out/ back.
IN_IMAGE = 'set -e; mkdir -p /tmp/work; cd /tmp/work; tar -xf -; "$@" >&2; tar -cf - -C out .'
ICON_LINES = (
    "    bitmap_icon = System.Drawing.Bitmap.FromStream(System.IO.MemoryStream(icon))\n"
    '    ghpython_root.SetDrawingBitmap("IconOverride", bitmap_icon)\n'
)
COMMANDS = ("build", "deploy", "status", "uninstall")
# Modules that exist only inside Rhino: a component importing them is not broken.
RHINO_ONLY = {
    "System", "Rhino", "Grasshopper", "GhPython", "ghpythonlib", "scriptcontext",
    "rhinoscriptsyntax", "rhinoscript", "clr", "Eto", "RhinoCodePlatform",
}


def componentizer_sha():
    """The pin lives in the Dockerfile; local and CI builds use the same componentizer."""
    dockerfile = open(os.path.join(os.path.dirname(HERE), "Dockerfile"), encoding="utf-8").read()
    return re.search(r"^ARG COMPONENTIZER_SHA=(\w+)$", dockerfile, re.M).group(1)


def load_componentizer(sha):
    cache = os.path.join(os.path.expanduser("~/.cache/ghuser-builder"), f"componentize_cpy-{sha}.py")
    if not os.path.exists(cache):
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        url = f"https://raw.githubusercontent.com/compas-dev/compas-actions.ghpython_components/{sha}/componentize_cpy.py"
        urllib.request.urlretrieve(url, cache)
    source = open(cache, encoding="utf-8").read()
    if ICON_LINES not in source:
        sys.exit("ghuser_dev: the pinned componentizer changed shape; update ICON_LINES")
    # Drop only the canvas-icon step (see the docstring); everything else is upstream.
    source = source.replace(ICON_LINES, "    pass  # ghuser_dev: no canvas icon outside Rhino on macOS\n")
    module = type(sys)("componentize_cpy")
    module.__file__ = cache
    exec(compile(source, cache, "exec"), module.__dict__)
    return module


def start_rhino_dotnet():
    if platform.system() != "Darwin":
        sys.exit("ghuser_dev: --builder rhino is macOS only; use --builder docker")
    if not os.path.isdir(RHINO):
        sys.exit(f"ghuser_dev: Rhino 8 not found at {RHINO}")
    os.environ["DOTNET_ROOT"] = os.path.join(RHINO, "dotnet", platform.machine())
    from pythonnet import load

    load("coreclr")
    import clr
    import System

    # GH_IO references System.Windows.Forms and System.Drawing; Rhino ships both.
    # LoadFrom, not clr.AddReference(path): on the .NET 10 that Rhino 8.36 ships,
    # pythonnet 3.0.5 resolves a path as an assembly name and cannot find it.
    sys.path += [os.path.join(RHINO, "ManagedPlugIns", "GrasshopperPlugin.rhp"), RHINO]
    System.Reflection.Assembly.LoadFrom(os.path.join(RHINO, "System.Drawing.Common.dll"))
    clr.AddReference("GH_IO")
    from GH_IO.Serialization import GH_LooseChunk

    return System, GH_LooseChunk


# --- sources -------------------------------------------------------------------


def requirements(code):
    return [r for line in code.splitlines() for m in [re.match(r"#\s*r\s*:(.*)$", line)] if m
            for r in split_requirements(m.group(1))]


def imported_modules(code):
    """Top-level modules a component imports, anywhere in it, that should import outside Rhino too."""
    names = set()
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
    return sorted(names - RHINO_ONLY - set(sys.stdlib_module_names))


# --- build ---------------------------------------------------------------------


def default_builder():
    return "docker"


def embedded_code(staged, prefix=""):
    """{component name: code} as the staged build embeds it, to compare with the canvas."""
    import verify_ghuser

    embedded = {}
    for d in bundles(staged):
        code_py = os.path.join(staged, d, "code.py")
        if os.path.isfile(code_py):
            text = open(code_py, encoding="utf-8").read()
            meta = json.load(open(os.path.join(staged, d, "metadata.json"), encoding="utf-8"))
            embedded[prefix + meta["name"]] = verify_ghuser.expected_code(text, VERSION, meta["name"], d + ".ghuser")
    return embedded


def build_with_rhino(staged, built, prefix):
    System, GH_LooseChunk = start_rhino_dotnet()
    cz = load_componentizer(componentizer_sha())
    import verify_ghuser

    verify_ghuser.use_ghio(System, GH_LooseChunk)
    os.makedirs(built)
    for d in bundles(staged):
        cz.create_ghuser_component(os.path.join(staged, d), os.path.join(built, d + ".ghuser"), VERSION, prefix or None)
    if not verify_ghuser.verify_all(staged, built, VERSION, prefix, canvas_icon=False):
        sys.exit(1)


def docker_command(prefix, image):
    """`docker run` for ghuser-build in the image, on components/ sent as a tar stream."""
    cmd = ["docker", "run", "-i", "--rm", "-e", "HOME=/tmp", image, "sh", "-c", IN_IMAGE, "sh",
           "ghuser-build", "--version", VERSION]
    if prefix:
        cmd += ["--prefix", prefix]
    return cmd + ["components", "out"]


def build_with_docker(staged, built, prefix, image):
    sent = io.BytesIO()
    with tarfile.open(fileobj=sent, mode="w") as tar:
        tar.add(staged, arcname="components")
    try:
        run = subprocess.run(docker_command(prefix, image), input=sent.getvalue(), capture_output=True)
    except FileNotFoundError:
        sys.exit("ghuser_dev: docker not found; install Docker Desktop (or OrbStack, colima) and start it")
    log = run.stderr.decode("utf-8", "replace")
    if run.returncode:
        sys.exit(f"{log}\nghuser_dev: ghuser-build in {image} failed. No image? Build it once:\n"
                 f"  docker build -t {image} <ghuser-builder checkout or git URL>")
    # Mono's warnings and the componentizer's progress are noise when it worked.
    for line in log.splitlines():
        if line.startswith("[verified]"):
            print(line)
    with tempfile.TemporaryDirectory() as back:
        with tarfile.open(fileobj=io.BytesIO(run.stdout)) as tar:
            tar.extractall(back, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
        shutil.copytree(os.path.join(back, "ghuser"), built)


def read_stamps(out):
    try:
        return json.load(open(os.path.join(out, STAMPS), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def changes(before, after):
    """What a rebuild means for Grasshopper: [(folder, what to do)]."""
    notes = []
    for d in sorted(set(before) | set(after)):
        old, new = before.get(d), after.get(d)
        if old == new:
            continue
        if old is None:
            notes.append((d, "new: restart Rhino to see it in the toolbar"))
        elif new is None:
            notes.append((d, "removed: restart Rhino; copies on the canvas now stop"))
        elif old["interface"] != new["interface"]:
            notes.append((d, "inputs, outputs or icon changed: restart Rhino, then replace it on the canvas"))
        else:
            notes.append((d, "code.py changed: replace it on the canvas"))
    return notes


def build(src, out, env=None, prefix="", builder=None, image=None):
    """Build and verify into out, and write its stamps. Returns {component name: embedded code} for deploy."""
    builder = builder or default_builder()
    env = os.path.abspath(env) if env else None
    out = os.path.abspath(out)
    with tempfile.TemporaryDirectory() as stage:
        # Staged here, not in the image: the stale check names files on this machine.
        # The componentizer embeds code.py verbatim, and the verifier checks against it.
        staged = os.path.join(stage, "components")
        prints = staging.stage(src, staged, env, os.path.join(out, STAMPS))
        built = os.path.join(stage, "ghuser")
        if builder == "rhino":
            build_with_rhino(staged, built, prefix)
        else:
            build_with_docker(staged, built, prefix, image or os.environ.get("GHUSER_BUILDER_IMAGE") or IMAGE)
        embedded = embedded_code(staged, prefix)
        before = read_stamps(out)
        # Replace, not add: a removed or renamed component must not keep loading.
        os.makedirs(out, exist_ok=True)
        for f in os.listdir(out):
            if f.endswith(".ghuser"):
                os.remove(os.path.join(out, f))
        for f in os.listdir(built):
            shutil.copy2(os.path.join(built, f), os.path.join(out, f))
        # Last, so a component never sees stamps whose file is not there yet.
        with open(os.path.join(out, STAMPS), "w", encoding="utf-8") as f:
            json.dump(prints, f, indent=1, sort_keys=True)

    print(f"ghuser_dev: wrote {os.path.relpath(out)}/ (dev build with {builder}: version {VERSION}"
          + (", no canvas icon" if builder == "rhino" else "")
          + (f", imports from {env})" if env else ")"))
    for d, note in changes(before, prints):
        print(f"ghuser_dev: {d} {note}")
    return embedded


# --- Grasshopper's User Object folder -------------------------------------------


def user_objects():
    return os.environ.get("GHUSER_USEROBJECTS") or USER_OBJECTS


def packages():
    return os.environ.get("GHUSER_PACKAGES") or PACKAGES


# A link is a symlink on macOS and a directory junction on Windows, which needs
# neither admin rights nor Developer Mode. os.path.islink() is False for a junction.


def is_link(path):
    if os.path.islink(path):
        return True
    try:
        return getattr(os.lstat(path), "st_reparse_tag", None) == getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", -1)
    except OSError:
        return False


def make_link(out, target):
    if WINDOWS:
        import _winapi

        _winapi.CreateJunction(out, target)
    else:
        os.symlink(out, target)


def remove_link(path):
    # rmdir removes a junction without touching what it points at; unlink a symlink.
    if WINDOWS and not os.path.islink(path):
        os.rmdir(path)
    else:
        os.unlink(path)


def links_to(out, uo):
    """Entries of uo that are links to out."""
    if not os.path.isdir(uo):
        return []
    want = os.path.realpath(out)
    return sorted(e for e in os.listdir(uo)
                  if is_link(os.path.join(uo, e)) and os.path.realpath(os.path.join(uo, e)) == want)


def ghuser_files(uo, follow):
    """{file name: [paths]} for every .ghuser under uo, through links when follow."""
    found = {}
    for dirpath, dirnames, filenames in os.walk(uo, followlinks=follow):
        if not follow:  # os.walk would go through a junction
            dirnames[:] = [d for d in dirnames if not is_link(os.path.join(dirpath, d))]
        for f in filenames:
            if f.endswith(".ghuser"):
                found.setdefault(f, []).append(os.path.join(dirpath, f))
    return found


def installed_copies(names, root):
    """{file name: [paths]} for .ghuser files in names that an installed package also carries."""
    found = ghuser_files(root, follow=False) if os.path.isdir(root) else {}
    return {f: ps for f, ps in found.items() if f in names}


def backup(uo, paths):
    """Move paths (inside uo) to the backups folder, under <time>/ and where they were; drop emptied folders."""
    backups = os.environ.get("GHUSER_BACKUPS") or os.path.expanduser("~/.cache/ghuser-builder/backups")
    root = os.path.join(backups, time.strftime("%Y%m%d-%H%M%S"))
    for p in paths:
        dest = os.path.join(root, os.path.relpath(p, uo))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(p, dest)
        parent = os.path.dirname(p)
        while parent != uo and os.path.isdir(parent) and not is_link(parent) and not os.listdir(parent):
            os.rmdir(parent)
            parent = os.path.dirname(parent)
    return root


def link(out, name, uo):
    """Link out into uo as name, so Grasshopper loads exactly one copy of each component. Returns messages."""
    out = os.path.abspath(out)
    os.makedirs(uo, exist_ok=True)
    notes = []
    target = os.path.join(uo, name)
    for other in links_to(out, uo):
        if other != name:
            remove_link(os.path.join(uo, other))
            notes.append(f"removed the older link {other}")
    if is_link(target):
        if os.path.realpath(target) != os.path.realpath(out):
            notes.append(f"{name} pointed at {os.path.realpath(target)}; now {out}")
            remove_link(target)
    elif os.path.exists(target):
        notes.append(f"{name} was a folder; moved to {backup(uo, [target])}")
    if not is_link(target):
        make_link(out, target)

    mine = {f for f in os.listdir(out) if f.endswith(".ghuser")}
    # Loose copies are ours to move; files behind someone else's link belong to
    # another checkout, so only say that they collide.
    loose = [p for f, ps in ghuser_files(uo, follow=False).items() if f in mine for p in ps]
    if loose:
        notes.append(f"moved {len(loose)} older copies to {backup(uo, loose)}")
    for f, ps in sorted(ghuser_files(uo, follow=True).items()):
        others = [p for p in ps if not p.startswith(target + os.sep)]
        if f in mine and others:
            notes.append(f"WARNING {f} also comes from {', '.join(others)}")
    return notes


def status(out, uo):
    """Print where out is linked and what is wrong; return the problems."""
    problems = []
    print(f"ghuser_dev: User Object folder {uo}")
    names = links_to(out, uo)
    built = sorted(f for f in os.listdir(out) if f.endswith(".ghuser")) if os.path.isdir(out) else []
    if names:
        print(f"ghuser_dev: {os.path.abspath(out)} is linked as {', '.join(names)}: {len(built)} components")
    else:
        problems.append(f"{out} is not linked into Grasshopper; run deploy")
    if not built:
        problems.append(f"{out} holds no .ghuser files; run build or deploy")
    if os.path.isdir(uo):
        for e in sorted(os.listdir(uo)):
            if is_link(os.path.join(uo, e)) and not os.path.exists(os.path.join(uo, e)):
                problems.append(f"{e} is a link to {os.readlink(os.path.join(uo, e))}, which is gone")
        for f, ps in sorted(ghuser_files(uo, follow=True).items()):
            if len(ps) > 1:
                problems.append(f"{f} loads {len(ps)} times: {', '.join(ps)}")
    for f, ps in sorted(installed_copies(set(built), packages()).items()):
        problems.append(f"{f} is also in an installed package ({', '.join(ps)}): Grasshopper loads both;"
                        " uninstall the package in the Package Manager while you develop")
    for p in problems:
        print(f"ghuser_dev: PROBLEM {p}")
    if not problems:
        print("ghuser_dev: nothing wrong")
    return problems


def uninstall(out, uo):
    names = links_to(out, uo)
    for n in names:
        remove_link(os.path.join(uo, n))
        print(f"ghuser_dev: removed {os.path.join(uo, n)}")
    if not names:
        print(f"ghuser_dev: {out} is not linked in {uo}")
    stamps = os.path.join(out, STAMPS)
    if os.path.exists(stamps):
        os.remove(stamps)
        print("ghuser_dev: dev components still on a canvas now stop; replace them from the installed package")


# --- Rhino's Python ------------------------------------------------------------

CHECK = r"""
import importlib, importlib.metadata as md, json, re, sys
reqs, mods = json.loads(sys.argv[1]), json.loads(sys.argv[2])
try:
    from packaging.requirements import Requirement
except ImportError:
    Requirement = None
result = {"missing": [], "imports": {}}
for spec in reqs:
    name = Requirement(spec).name if Requirement else re.split(r"[<>=!~ \[;]", spec)[0]
    try:
        have = md.version(name)
    except md.PackageNotFoundError:
        result["missing"].append(spec)
        continue
    if Requirement and not Requirement(spec).specifier.contains(have, prereleases=True):
        result["missing"].append(spec + " (have " + have + ")")
for m in mods:
    try:
        importlib.import_module(m)
        result["imports"][m] = None
    except ModuleNotFoundError as e:
        rhino = e.name and e.name.split(".")[0] in %r
        result["imports"][m] = "rhino" if rhino else "%%s: %%s" %% (type(e).__name__, e)
    except Exception as e:
        result["imports"][m] = "%%s: %%s" %% (type(e).__name__, e)
print(json.dumps(result))
""" % sorted(RHINO_ONLY)


def site_env():
    """The folder Rhino installs `# r:` packages into: its newest default site env."""
    root = os.path.join(RHINO_PYTHON, "site-envs")
    envs = [os.path.join(root, d) for d in os.listdir(root) if d.startswith("default")] if os.path.isdir(root) else []
    return max(envs, key=os.path.getmtime) if envs else None


def check_rhino_python(src, env, install):
    """Check requirements and imports in Rhino's own CPython. Returns the problems."""
    python, site = os.path.join(RHINO_PYTHON, PYTHON_EXE), site_env()
    if not os.path.isfile(python) or not site:
        return [f"Rhino's Python not found at {RHINO_PYTHON}: start Rhino 8 once and open the ScriptEditor"]
    header = env_header(os.path.abspath(env) if env else None)
    reqs, mods = set(), set()
    for d in bundles(src):
        code_py = os.path.join(src, d, "code.py")
        if os.path.isfile(code_py):
            code = dev_code(open(code_py, encoding="utf-8").read(), header)
            reqs.update(requirements(code))
            mods.update(imported_modules(code))
    path = os.pathsep.join(p for p in (os.path.abspath(env) if env else None, site) if p)

    def run():
        out = subprocess.run([python, "-s", "-c", CHECK, json.dumps(sorted(reqs)), json.dumps(sorted(mods))],
                             env={**os.environ, "PYTHONPATH": path}, capture_output=True, text=True)
        if out.returncode:
            sys.exit(f"ghuser_dev: the check in Rhino's Python failed:\n{out.stderr}")
        return json.loads(out.stdout.strip().splitlines()[-1])

    result = run()
    if result["missing"] and install:
        specs = [m.split(" (have ")[0] for m in result["missing"]]
        print(f"ghuser_dev: installing into Rhino's Python ({site}): {' '.join(specs)}")
        subprocess.run([python, "-m", "pip", "install", "--upgrade", "--target", site, *specs], check=True)
        result = run()
    problems = [f"`# r: {m}` is not installed in Rhino's Python; rerun with --requirements" for m in result["missing"]]
    for m, error in sorted(result["imports"].items()):
        if error is None:
            print(f"ghuser_dev: Rhino's Python imports {m}")
        elif error == "rhino":
            print(f"ghuser_dev: {m} needs Rhino itself to import; not checked")
        else:
            problems.append(f"Rhino's Python cannot import {m}: {error}")
    return problems


# --- a running Rhino -----------------------------------------------------------

RELOAD = r"""
import ast, base64, json, os, sys
ENV, CODE, REPORT = %r, %r, %r
result = {"dropped": [], "elsewhere": [], "recomputed": [], "stale": [], "error": None}


def same_code(a, b):
    # Placing a component writes its inputs' type hints into RunScript's signature,
    # so compare without annotations; comments too, since `# env:` and `# r:` matter.
    def key(code):
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                node.returns = None
                args = node.args
                for arg in args.posonlyargs + args.args + args.kwonlyargs + [args.vararg, args.kwarg]:
                    if arg is not None:
                        arg.annotation = None
        comments = [line.strip() for line in code.splitlines() if line.strip().startswith("#")]
        return ast.dump(tree), comments
    return key(a) == key(b)

if ENV:
    # Every module named like a package in ENV goes, wherever it came from: one
    # left from an installed .yak would otherwise stand in for the working copy.
    names = {os.path.splitext(e)[0] for e in os.listdir(ENV)
             if e.endswith(".py") or os.path.isfile(os.path.join(ENV, e, "__init__.py"))}
    for name, module in list(sys.modules.items()):
        path = getattr(module, "__file__", None)
        inside = path and os.path.normcase(os.path.realpath(path)).startswith(os.path.normcase(ENV) + os.sep)
        if inside or name.split(".")[0] in names:
            del sys.modules[name]
            result["dropped"].append(name)
            if path and not inside and "." not in name:
                result["elsewhere"].append(name + " from " + os.path.dirname(os.path.dirname(path)))
try:
    import Grasshopper
    from GH_IO.Serialization import GH_LooseChunk
    canvas = Grasshopper.Instances.ActiveCanvas
    doc = canvas.Document if canvas else None
    for obj in list(doc.Objects) if doc else []:
        if obj.Name not in CODE:
            continue
        chunk = GH_LooseChunk("UserObject")
        obj.Write(chunk)
        script = chunk.FindChunk("Script")
        code = base64.b64decode(script.GetString("Text")).decode("utf-8") if script else None
        stale = code is not None and not same_code(code.replace("\r\n", "\n"), CODE[obj.Name])
        result["stale" if stale else "recomputed"].append(obj.NickName or obj.Name)
        # A script component keeps the globals it compiled, so a core imported at
        # the top of code.py stays old; setting the same source recompiles it. A
        # stale one recompiles too, and its own check stops it.
        if hasattr(obj, "TryGetSource"):
            ok, source = obj.TryGetSource()
            if ok:
                obj.SetSource(source)
        obj.ExpireSolution(False)
    if result["recomputed"] or result["stale"]:
        doc.NewSolution(False)
except Exception as e:
    result["error"] = "%%s: %%s" %% (type(e).__name__, e)
with open(REPORT, "w") as f:
    json.dump(result, f)
"""


def reload_rhino(env, embedded):
    if not os.path.exists(RHINOCODE):
        return
    running = subprocess.run([RHINOCODE, "list"], capture_output=True, text=True).stdout.strip().splitlines()[1:]
    if not running:
        print("ghuser_dev: Rhino is not running; new components appear when it starts")
        return
    with tempfile.TemporaryDirectory() as tmp:
        report, script = os.path.join(tmp, "report.json"), os.path.join(tmp, "reload.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(RELOAD % (os.path.realpath(env) if env else None, embedded, report))
        subprocess.run([RHINOCODE, "script", script], capture_output=True, text=True, timeout=120)
        # rhinocode returns once Rhino has the script, not when it has run it.
        deadline = time.time() + 60
        while not os.path.exists(report) and time.time() < deadline:
            time.sleep(0.5)
        if not os.path.exists(report):
            print("ghuser_dev: could not reach the running Rhino; restart it to load the new build")
            return
        result = json.load(open(report))
    if result["dropped"]:
        print(f"ghuser_dev: Rhino forgot {len(result['dropped'])} modules of the core")
    for e in result["elsewhere"]:
        print(f"ghuser_dev: Rhino had {e} (an installed package?); it now imports from {env}")
    if result["recomputed"]:
        print(f"ghuser_dev: recomputed {', '.join(result['recomputed'])}")
    elif not result["stale"]:
        print("ghuser_dev: none of these components is on the open canvas")
    if result["stale"]:
        print(f"ghuser_dev: stopped on the canvas, older than this build: {', '.join(result['stale'])}")
    if result["error"]:
        print(f"ghuser_dev: reloading in Rhino failed: {result['error']}")


# --- command line --------------------------------------------------------------


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] not in COMMANDS and not argv[0].startswith("-"):
        argv.insert(0, "build")  # the original form: ghuser_dev.py SRC OUT
    ap = argparse.ArgumentParser(description="Dev builds of .ghuser components, linked into Grasshopper.")
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("build", "deploy"):
        p = sub.add_parser(name)
        p.add_argument("src", help="components folder")
        p.add_argument("out", help="output folder (e.g. build/ghuser-dev)")
        p.add_argument("--env", help="folder to put on Rhino's sys.path via `# env:` (e.g. src)")
        p.add_argument("--prefix", default="")
        p.add_argument("--builder", choices=("docker", "rhino"), default="docker", help="default: docker")
        p.add_argument("--image", help=f"builder image for --builder docker (default: $GHUSER_BUILDER_IMAGE or {IMAGE})")
    deploy = sub.choices["deploy"]
    deploy.add_argument("--name", help="link name in the User Object folder (default: <current folder>-dev)")
    deploy.add_argument("--requirements", action="store_true", help="install missing `# r:` packages into Rhino")
    deploy.add_argument("--no-reload", action="store_true", help="leave a running Rhino alone")
    for name in ("status", "uninstall"):
        sub.add_parser(name).add_argument("out", help="the folder deploy linked")
    a = ap.parse_args(argv)
    uo = user_objects()

    if a.command == "status":
        sys.exit(1 if status(a.out, uo) else 0)
    if a.command == "uninstall":
        return uninstall(a.out, uo)

    embedded = build(a.src, a.out, a.env, a.prefix, a.builder, a.image)
    if a.command == "build":
        print("ghuser_dev: point Grasshopper at it with `deploy`, or link it into the User Object folder")
        return

    name = a.name or os.path.basename(os.getcwd()) + "-dev"
    for note in link(a.out, name, uo):
        print(f"ghuser_dev: {note}")
    print(f"ghuser_dev: Grasshopper loads {a.out}/ as {os.path.join(uo, name)}")
    problems = check_rhino_python(a.src, a.env, a.requirements)
    if not a.no_reload:
        reload_rhino(a.env, embedded)
    for p in problems:
        print(f"ghuser_dev: PROBLEM {p}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
