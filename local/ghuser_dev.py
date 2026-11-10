# /// script
# requires-python = ">=3.10"
# dependencies = ["pythonnet==3.0.5"]
# ///
"""Development builds of .ghuser components with the Rhino 8 installed on this Mac.

    uv run <ghuser-builder>/local/ghuser_dev.py build components dist-dev [--env src]
    uv run <ghuser-builder>/local/ghuser_dev.py deploy components dist-dev [--env src]
    uv run <ghuser-builder>/local/ghuser_dev.py status dist-dev
    uv run <ghuser-builder>/local/ghuser_dev.py uninstall dist-dev

No Docker: it runs the same pinned componentizer on Rhino 8's own .NET runtime
and GH_IO.dll, so the files match exactly the Rhino you will load them in.
`ghuser_dev.py components dist-dev` (no command) is `build`, as before.

build      componentize and verify into OUT, replacing what was there.
deploy     build, then link OUT into Grasshopper's User Object folder as NAME
           (default: <current folder>-dev). Loose copies of the same components
           elsewhere in that folder move to ~/.cache/ghuser-builder/backups/<time>/, so
           Grasshopper loads one of each. Then checks, in Rhino's own Python, the
           `# r:` requirements and that what the components import imports; with
           Rhino running, drops modules loaded from --env and recomputes the
           components on the canvas, listing any that carry older code.
             --requirements  install missing `# r:` packages into Rhino, visibly
             --no-reload     leave a running Rhino alone
status     where OUT is linked, and anything that will go wrong when it loads.
uninstall  remove the links to OUT. Backups stay where deploy put them.

--env PATH   prepends `# env: <absolute PATH>` to every component, so Rhino imports
             your core library straight from the working copy. Edit, recompute,
             no reinstall. (The idea comes from the ChiaChing-Yen fork of the
             compas componentizer.) A `# r:` pin on {{version}} names that same
             library, so a dev build with --env leaves it out: 0.0.0-dev.local
             is on no index.

DEV ONLY, by design:
  * no canvas icon: Rhino's macOS System.Drawing cannot create a bitmap outside a
    running Rhino, so components show the default script icon on the canvas (the
    toolbar icon is unaffected);
  * no .yak, and the version is always 0.0.0-dev.local;
  * `# env:` paths only exist on this machine.
Releases come from CI (ghuser-build in the Linux image), which has full icons.

GHUSER_USEROBJECTS and GHUSER_BACKUPS override the User Object and backup folders (tests use them).
"""

import argparse
import ast
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
RHINO = "/Applications/Rhino 8.app/Contents/Frameworks/RhCore.framework/Versions/A/Resources"
RHINOCODE = "/Applications/Rhino 8.app/Contents/Resources/bin/rhinocode"
RHINO_PYTHON = os.path.expanduser("~/.rhinocode/py39-rh8")
USER_OBJECTS = os.path.expanduser(
    "~/Library/Application Support/McNeel/Rhinoceros/8.0/Plug-ins/"
    "Grasshopper (b45a29b1-4343-4035-989e-044e8580d9cf)/UserObjects"
)
VERSION = "0.0.0-dev.local"
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
        sys.exit("ghuser_dev: macOS with Rhino 8 only. Elsewhere, use the Docker image (templates/local/ghuser).")
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


def bundles(src):
    return sorted(
        d for d in os.listdir(src)
        if os.path.isdir(os.path.join(src, d)) and d not in ("__pycache__", ".git")
    )


def split_requirements(line):
    """`numpy>=1,<2, scipy` -> ['numpy>=1,<2', 'scipy']: a comma starts a new one only before a name."""
    return [r.strip() for r in re.split(r",\s*(?=[A-Za-z])", line) if r.strip()]


def dev_code(code, header):
    """code.py as a dev build embeds it: the `# env:` header, and with it no `# r:` pin on {{version}}."""
    if not header:
        return code
    lines = []
    for line in code.splitlines(keepends=True):
        m = re.match(r"#\s*r\s*:(.*)$", line.rstrip("\r\n"))
        if m and "{{version}}" in m.group(1):
            kept = [r for r in split_requirements(m.group(1)) if "{{version}}" not in r]
            if not kept:
                continue
            line = "# r: " + ", ".join(kept) + "\n"
        lines.append(line)
    return header + "".join(lines)


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


def build(src, out, env=None, prefix=""):
    """Build and verify into out. Returns {component name: embedded code} for deploy."""
    System, GH_LooseChunk = start_rhino_dotnet()
    cz = load_componentizer(componentizer_sha())
    sys.path.insert(0, TOOLS)
    import verify_ghuser

    verify_ghuser.use_ghio(System, GH_LooseChunk)
    header = f"# env: {os.path.abspath(env)}\n" if env else ""
    embedded = {}

    with tempfile.TemporaryDirectory() as stage:
        work = os.path.join(stage, "components")
        shutil.copytree(src, work, ignore=shutil.ignore_patterns("__pycache__"))
        # The componentizer embeds code.py verbatim, so change the copy; the
        # verifier then checks the files against exactly what went in.
        for d in bundles(work):
            code = os.path.join(work, d, "code.py")
            if os.path.isfile(code):
                text = dev_code(open(code, encoding="utf-8").read(), header)
                open(code, "w", encoding="utf-8").write(text)
                meta = json.load(open(os.path.join(work, d, "metadata.json"), encoding="utf-8"))
                embedded[prefix + meta["name"]] = verify_ghuser.expected_code(
                    text, VERSION, meta["name"], d + ".ghuser")
        built = os.path.join(stage, "ghuser")
        os.makedirs(built)
        for d in bundles(work):
            cz.create_ghuser_component(os.path.join(work, d), os.path.join(built, d + ".ghuser"), VERSION, prefix or None)
        if not verify_ghuser.verify_all(work, built, VERSION, prefix, canvas_icon=False):
            sys.exit(1)
        # Replace, not add: a removed or renamed component must not keep loading.
        os.makedirs(out, exist_ok=True)
        for f in os.listdir(out):
            if f.endswith(".ghuser"):
                os.remove(os.path.join(out, f))
        for f in os.listdir(built):
            shutil.copy2(os.path.join(built, f), os.path.join(out, f))

    print(f"ghuser_dev: wrote {out}/ (dev build: version {VERSION}, no canvas icon"
          + (f", imports from {os.path.abspath(env)})" if env else ")"))
    return embedded


# --- Grasshopper's User Object folder -------------------------------------------


def user_objects():
    return os.environ.get("GHUSER_USEROBJECTS") or USER_OBJECTS


def links_to(out, uo):
    """Entries of uo that are links to out."""
    if not os.path.isdir(uo):
        return []
    want = os.path.realpath(out)
    return sorted(e for e in os.listdir(uo)
                  if os.path.islink(os.path.join(uo, e)) and os.path.realpath(os.path.join(uo, e)) == want)


def ghuser_files(uo, follow):
    """{file name: [paths]} for every .ghuser under uo, through links when follow."""
    found = {}
    for dirpath, dirnames, filenames in os.walk(uo, followlinks=follow):
        for f in filenames:
            if f.endswith(".ghuser"):
                found.setdefault(f, []).append(os.path.join(dirpath, f))
    return found


def backup(uo, paths):
    """Move paths (inside uo) to the backups folder, under <time>/ and where they were; drop emptied folders."""
    backups = os.environ.get("GHUSER_BACKUPS") or os.path.expanduser("~/.cache/ghuser-builder/backups")
    root = os.path.join(backups, time.strftime("%Y%m%d-%H%M%S"))
    for p in paths:
        dest = os.path.join(root, os.path.relpath(p, uo))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(p, dest)
        parent = os.path.dirname(p)
        while parent != uo and os.path.isdir(parent) and not os.path.islink(parent) and not os.listdir(parent):
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
            os.unlink(os.path.join(uo, other))
            notes.append(f"removed the older link {other}")
    if os.path.islink(target):
        if os.path.realpath(target) != os.path.realpath(out):
            notes.append(f"{name} pointed at {os.readlink(target)}; now {out}")
            os.unlink(target)
    elif os.path.exists(target):
        notes.append(f"{name} was a folder; moved to {backup(uo, [target])}")
    if not os.path.islink(target):
        os.symlink(out, target)

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
            if os.path.islink(os.path.join(uo, e)) and not os.path.exists(os.path.join(uo, e)):
                problems.append(f"{e} is a link to {os.readlink(os.path.join(uo, e))}, which is gone")
        for f, ps in sorted(ghuser_files(uo, follow=True).items()):
            if len(ps) > 1:
                problems.append(f"{f} loads {len(ps)} times: {', '.join(ps)}")
    for p in problems:
        print(f"ghuser_dev: PROBLEM {p}")
    if not problems:
        print("ghuser_dev: nothing wrong")
    return problems


def uninstall(out, uo):
    names = links_to(out, uo)
    for n in names:
        os.unlink(os.path.join(uo, n))
        print(f"ghuser_dev: removed {os.path.join(uo, n)}")
    if not names:
        print(f"ghuser_dev: {out} is not linked in {uo}")


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
    python, site = os.path.join(RHINO_PYTHON, "python3.9"), site_env()
    if not os.path.isfile(python) or not site:
        return [f"Rhino's Python not found at {RHINO_PYTHON}: start Rhino 8 once and open the ScriptEditor"]
    header = f"# env: {os.path.abspath(env)}\n" if env else ""
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
import base64, json, os, sys
ENV, CODE, REPORT = %r, %r, %r
result = {"dropped": [], "recomputed": [], "stale": [], "error": None}
if ENV:
    for name, module in list(sys.modules.items()):
        path = getattr(module, "__file__", None)
        if path and os.path.realpath(path).startswith(ENV + os.sep):
            del sys.modules[name]
            result["dropped"].append(name)
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
        if code is not None and code.replace("\r\n", "\n") != CODE[obj.Name]:
            result["stale"].append(obj.NickName or obj.Name)
        else:
            obj.ExpireSolution(False)
            result["recomputed"].append(obj.NickName or obj.Name)
    if result["recomputed"]:
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
        print(f"ghuser_dev: Rhino forgot {len(result['dropped'])} modules from {env}")
    if result["recomputed"]:
        print(f"ghuser_dev: recomputed {', '.join(result['recomputed'])}")
    if result["stale"]:
        print(f"ghuser_dev: older code on the canvas, replace from the toolbar: {', '.join(result['stale'])}")
    if result["error"]:
        print(f"ghuser_dev: reloading in Rhino failed: {result['error']}")
    print("ghuser_dev: components new to this build appear after restarting Grasshopper")


# --- command line --------------------------------------------------------------


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] not in COMMANDS and not argv[0].startswith("-"):
        argv.insert(0, "build")  # the original form: ghuser_dev.py SRC OUT
    ap = argparse.ArgumentParser(description="Dev builds with the installed Rhino 8 (macOS).")
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("build", "deploy"):
        p = sub.add_parser(name)
        p.add_argument("src", help="components folder")
        p.add_argument("out", help="output folder (e.g. build/ghuser-dev)")
        p.add_argument("--env", help="folder to put on Rhino's sys.path via `# env:` (e.g. src)")
        p.add_argument("--prefix", default="")
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

    embedded = build(a.src, a.out, a.env, a.prefix)
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
