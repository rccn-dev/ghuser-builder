# /// script
# requires-python = ">=3.10,<3.14"
# ///
"""The dev-loop scenarios (tests/scenarios.py) in a running Rhino 8: the canvas for real.

    uv run tests/rhino/run_scenarios.py [--image ghuser-builder:local] [-k text]

Needs Rhino 8 running (macOS or Windows; Grasshopper is opened if it is not) and Docker
with the builder image. Not headless, and not for CI: run it before a release, on each OS,
and record the result in docs/validation.md's Status table. It checks what tests/canvas.py
assumes: that Rhino compiles a dev component's top level with `ghenv`, shows the label
and the reason, runs RELOAD as written, and keeps a placed component's code in a saved file.

For every scenario it builds a scratch project under ~/.cache/ghuser-builder/scenarios,
places each component from its .ghuser file in a new Grasshopper document (radius 1,
count 4), makes the changes, deploys (build + reload, no link: nothing is added to the
User Object folder), saves, closes and reopens the document, and places fresh copies.
It leaves the document closed and the scratch folder removed. What it cannot check is
the toolbar, which Grasshopper reads only at startup: see docs/validation.md.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "local"))
sys.path.insert(0, str(HERE.parent))
import ghuser_dev  # noqa: E402
from scenarios import SCENARIOS, UNINSTALL, UPGRADE, component_names, make_project  # noqa: E402

SCRATCH = Path.home() / ".cache" / "ghuser-builder" / "scenarios"

# Runs inside Rhino. ARGS and OUT are filled in per call.
DRIVER = r'''
import json, sys, traceback
ARGS, OUT = %r, %r
result = {"components": {}}
try:
    import Rhino, System
    import Grasshopper
    from Grasshopper.Kernel import GH_RuntimeMessageLevel as Level

    Rhino.RhinoApp.GetPlugInObject("Grasshopper").ShowEditor()
    server, canvas = Grasshopper.Instances.DocumentServer, Grasshopper.Instances.ActiveCanvas
    action = ARGS["action"]

    def find(guid):
        return canvas.Document.FindObject(System.Guid(guid), True)

    if action == "new":
        doc = Grasshopper.Kernel.GH_Document()
        server.AddDocument(doc)
        canvas.Document = doc
    elif action == "place":
        obj = Grasshopper.Kernel.GH_UserObject(ARGS["path"]).InstantiateObject()
        obj.CreateAttributes()
        obj.Attributes.Pivot = System.Drawing.PointF(200, 100 + 120 * len(canvas.Document.Objects) / 3)
        canvas.Document.AddObject(obj, False)
        for i, value in enumerate((1, 4)):
            slider = Grasshopper.Kernel.Special.GH_NumberSlider()
            slider.CreateAttributes()
            slider.Slider.Minimum, slider.Slider.Maximum = System.Decimal(0), System.Decimal(10)
            slider.Slider.DecimalPlaces = 0
            slider.SetSliderValue(System.Decimal(value))
            canvas.Document.AddObject(slider, False)
            obj.Params.Input[i].AddSource(slider)
        result["guid"] = str(obj.InstanceGuid)
    elif action == "save":
        Grasshopper.Kernel.GH_DocumentIO(canvas.Document).SaveQuiet(ARGS["path"])
    elif action == "close":
        doc = canvas.Document
        if doc is not None:
            doc.Enabled = False
            server.RemoveDocument(doc)
            canvas.Document = None
    elif action == "open":
        io = Grasshopper.Kernel.GH_DocumentIO()
        io.Open(ARGS["path"])
        server.AddDocument(io.Document)
        canvas.Document = io.Document
        io.Document.Enabled = True
    elif action == "foreign":
        for name in [n for n in sys.modules if n == ARGS["module"] or n.startswith(ARGS["module"] + ".")]:
            del sys.modules[name]
        sys.path.insert(0, ARGS["folder"])
        __import__(ARGS["module"])
        sys.path.remove(ARGS["folder"])

    if action in ("place", "solve", "open"):
        canvas.Document.NewSolution(True)
        for guid in ARGS.get("guids", []) + ([result["guid"]] if "guid" in result else []):
            obj = find(guid)
            if obj is None:
                result["components"][guid] = {"state": "missing"}
                continue
            errors = [str(m) for m in obj.RuntimeMessages(Level.Error)]
            data = obj.Params.Output[0].VolatileData
            points = list(data.AllData(True)) if data.DataCount else []
            result["components"][guid] = {
                "level": str(obj.RuntimeMessageLevel), "label": obj.Message or "", "errors": errors,
                "z": points[0].Value.Z if points and hasattr(points[0], "Value") and hasattr(points[0].Value, "Z") else None,
            }
except Exception:
    result["error"] = traceback.format_exc()
with open(OUT, "w") as f:
    json.dump(result, f)
'''


def rhino(action, **args):
    """Run one driver action in the running Rhino; returns its result."""
    with tempfile.TemporaryDirectory() as tmp:
        out, script = os.path.join(tmp, "out.json"), os.path.join(tmp, "driver.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(DRIVER % ({"action": action, **args}, out))
        subprocess.run([ghuser_dev.RHINOCODE, "script", script], capture_output=True, text=True, timeout=120)
        deadline = time.time() + 60
        while not os.path.exists(out) and time.time() < deadline:
            time.sleep(0.3)
        if not os.path.exists(out):
            raise RuntimeError(f"Rhino did not answer {action}")
        result = json.load(open(out))
    if result.get("error"):
        raise RuntimeError(f"{action} failed in Rhino:\n{result['error']}")
    return result


def outcome(state):
    """The same vocabulary as tests/canvas.py: "ran", or the label it stops with."""
    if state.get("level") in ("Blank", "Remark") and not state.get("errors"):
        return "ran"
    return state.get("label") or "failed: " + "; ".join(state.get("errors", []))


def run_scenario(scenario, image, log):
    problems = []

    def expect(what, state, want, z=None):
        got = outcome(state)
        if got != want:
            problems.append(f"{what}: {got!r}, expected {want!r} ({state})")
        elif want == "ran" and z is not None and state.get("z") != z:
            problems.append(f"{what}: z = {state.get('z')}, expected {z}")
        elif want != "ran" and not any("ghuser-dev: " in e for e in state.get("errors", [])):
            log(f"  note: {what} shows {got!r} without the full reason: {state.get('errors')}")

    root = SCRATCH / scenario.name.replace(" ", "-").replace(",", "").replace("'", "")
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    project = make_project(root)
    stamps = ghuser_dev.stamps_path(project / "dist-dev")

    def deploy(project):
        embedded = ghuser_dev.build(str(project / "components"), str(project / "dist-dev"),
                                    str(project / "src"), "", "docker", image)
        ghuser_dev.reload_rhino(str(project / "src"), embedded, stamps)
        return embedded

    try:
        deploy(project)
        rhino("close")
        rhino("new")
        placed = {}
        for folder in component_names(project):
            r = rhino("place", path=str(project / "dist-dev" / f"{folder}.ghuser"))
            placed[folder] = r["guid"]
            expect(f"{folder} placed", r["components"][r["guid"]], "ran", 0.0)
        if scenario.foreign_core:
            installed = root / "installed"
            (installed / "ringkit").mkdir(parents=True)
            (installed / "ringkit" / "__init__.py").write_text(
                "def ring_points(radius, count, z=0.0):\n    return [(radius, 0.0, 99.0)] * count\n")
            rhino("foreign", folder=str(installed), module="ringkit")

        for step in scenario.steps:
            if step == UNINSTALL:
                ghuser_dev.uninstall(str(project / "dist-dev"), ghuser_dev.user_objects())
                ghuser_dev.reload_rhino(None, {}, stamps)
                continue
            if step == UPGRADE:
                ghuser_dev.staging.STALE_CHECK = ghuser_dev.staging.STALE_CHECK.replace(
                    "# ghuser-dev: stops", "# ghuser-dev 9: stops")
            else:
                project = step(project)
                stamps = ghuser_dev.stamps_path(project / "dist-dev")
            deploy(project)

        guids = list(placed.values())
        for when in ("after reload", "reopened"):
            if when == "reopened":
                gh = str(root / "scenario.gh")
                rhino("save", path=gh)
                rhino("close")
                states = rhino("open", path=gh, guids=guids)["components"]
            else:
                states = rhino("solve", guids=guids)["components"]
            for folder, want in scenario.old.items():
                expect(f"{folder} {when}", states[placed[folder]], want, scenario.z)

        if scenario.fresh:
            for folder, want in scenario.fresh.items():
                r = rhino("place", path=str(project / "dist-dev" / f"{folder}.ghuser"))
                expect(f"{folder} fresh", r["components"][r["guid"]], want, scenario.z)
    finally:
        rhino("close")
        shutil.rmtree(root, ignore_errors=True)
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--image", default=os.environ.get("GHUSER_BUILDER_IMAGE") or ghuser_dev.IMAGE)
    ap.add_argument("-k", default="", help="only scenarios whose name contains this")
    a = ap.parse_args()
    running = subprocess.run([ghuser_dev.RHINOCODE, "list"], capture_output=True, text=True).stdout.strip().splitlines()[1:]
    if not running:
        sys.exit("run_scenarios: start Rhino 8 first")
    original = ghuser_dev.staging.STALE_CHECK
    failed = []
    for scenario in [s for s in SCENARIOS if a.k in s.name]:
        ghuser_dev.staging.STALE_CHECK = original
        print(f"== {scenario.name}", flush=True)
        problems = run_scenario(scenario, a.image, print)
        for p in problems:
            print(f"  FAIL {p}")
        print("  ok" if not problems else "  FAILED", flush=True)
        if problems:
            failed.append(scenario.name)
    shutil.rmtree(SCRATCH, ignore_errors=True)
    print(f"\n{len(failed)} failed: {', '.join(failed)}" if failed else "\nall scenarios ok in Rhino")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
