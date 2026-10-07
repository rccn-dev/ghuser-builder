# /// script
# requires-python = ">=3.10"
# dependencies = ["pythonnet==3.0.5"]
# ///
"""Development builds of .ghuser components with the Rhino 8 installed on this Mac.

    uv run <ghuser-builder>/local/ghuser_dev.py components dist-dev
    uv run <ghuser-builder>/local/ghuser_dev.py components dist-dev --env src

No Docker: it runs the same pinned componentizer on Rhino 8's own .NET runtime
and GH_IO.dll, so the files match exactly the Rhino you will load them in.

--env PATH   prepends `# env: <absolute PATH>` to every component, so Rhino imports
             your core library straight from the working copy. Edit, recompute,
             no reinstall. (The idea comes from the ChiaChing-Yen fork of the
             compas componentizer.)

DEV ONLY, by design:
  * no canvas icon: Rhino's macOS System.Drawing cannot create a bitmap outside a
    running Rhino, so components show the default script icon on the canvas (the
    toolbar icon is unaffected);
  * no .yak, and the version is always 0.0.0-dev.local;
  * `# env:` paths only exist on this machine.
Releases come from CI (ghuser-build in the Linux image), which has full icons.
"""

import argparse
import os
import platform
import re
import shutil
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
RHINO = "/Applications/Rhino 8.app/Contents/Frameworks/RhCore.framework/Versions/A/Resources"
VERSION = "0.0.0-dev.local"
ICON_LINES = (
    "    bitmap_icon = System.Drawing.Bitmap.FromStream(System.IO.MemoryStream(icon))\n"
    '    ghpython_root.SetDrawingBitmap("IconOverride", bitmap_icon)\n'
)


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

    # GH_IO references System.Windows.Forms and System.Drawing; Rhino ships both.
    sys.path += [os.path.join(RHINO, "ManagedPlugIns", "GrasshopperPlugin.rhp"), RHINO]
    clr.AddReference(os.path.join(RHINO, "System.Drawing.Common.dll"))
    clr.AddReference("GH_IO")
    import System
    from GH_IO.Serialization import GH_LooseChunk

    return System, GH_LooseChunk


def main():
    ap = argparse.ArgumentParser(description="Dev builds with the installed Rhino 8 (macOS).")
    ap.add_argument("src", help="components folder")
    ap.add_argument("out", help="output folder (e.g. dist-dev)")
    ap.add_argument("--env", help="folder to put on Rhino's sys.path via `# env:` (e.g. src)")
    ap.add_argument("--prefix", default="")
    a = ap.parse_args()

    System, GH_LooseChunk = start_rhino_dotnet()
    cz = load_componentizer(componentizer_sha())
    sys.path.insert(0, TOOLS)
    import verify_ghuser

    verify_ghuser.use_ghio(System, GH_LooseChunk)
    header = f"# env: {os.path.abspath(a.env)}\n" if a.env else ""

    with tempfile.TemporaryDirectory() as stage:
        work = os.path.join(stage, "components")
        shutil.copytree(a.src, work, ignore=shutil.ignore_patterns("__pycache__"))
        if header:  # the componentizer embeds code.py verbatim, so add the line to the copy
            for d in os.listdir(work):
                code = os.path.join(work, d, "code.py")
                if os.path.isfile(code):
                    text = open(code, encoding="utf-8").read()
                    open(code, "w", encoding="utf-8").write(header + text)
        built = os.path.join(stage, "ghuser")
        os.makedirs(built)
        for d in sorted(os.listdir(work)):
            if os.path.isdir(os.path.join(work, d)) and d not in ("__pycache__", ".git"):
                cz.create_ghuser_component(os.path.join(work, d), os.path.join(built, d + ".ghuser"), VERSION, a.prefix or None)
        if not verify_ghuser.verify_all(a.src, built, VERSION, a.prefix, header, canvas_icon=False):
            sys.exit(1)
        os.makedirs(a.out, exist_ok=True)
        for f in os.listdir(built):
            shutil.copy2(os.path.join(built, f), os.path.join(a.out, f))

    print(f"ghuser_dev: wrote {a.out}/ (dev build: version {VERSION}, no canvas icon"
          + (f", imports from {os.path.abspath(a.env)})" if a.env else ")"))
    print("ghuser_dev: point Grasshopper at it, e.g. symlink into File > Special Folders > User Object Folder")


if __name__ == "__main__":
    main()
