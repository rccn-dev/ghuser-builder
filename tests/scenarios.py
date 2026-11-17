"""Dev-loop scenarios: what a developer edits, what deploy must say, what the canvas must then do.

One table, run on two canvases: tests/canvas.py (headless, tests/test_dev_scenarios.py)
and a running Rhino 8 (tests/rhino/run_scenarios.py). Each scenario starts from a
project with two components, A and B (example 03: a vendored core in src/), deploys
it, places A and B, makes its changes (deploying after each), then checks:

  notes   what deploy printed, per component folder (none for a folder not listed)
  old     what a component placed before the change does now, after deploy reloaded Rhino
          and again after the file is reopened: "ran", or the label it stops with. The label
          is the contract: the full reason shows too, unless the top of code.py fails first
          (a core that is gone), in which case Rhino shows that error.
  fresh   what one placed from the latest build does ("ran"); a folder not listed is not in the build
  z       the height of the first point when it ran: 1.0 once the core is edited
"""

import json
import shutil
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "03-vendored-core"
A, B = "RingPointsVendored", "RingPointsTwo"
REPLACE, RESTART, REMOVED, GONE = "dev: replace", "dev: restart, replace", "dev: removed", "dev: not deployed"


def add_component(project, source, folder):
    """Copy a component folder under a new name; the class and the component name follow it."""
    shutil.copytree(project / "components" / source, project / "components" / folder)
    code = project / "components" / folder / "code.py"
    code.write_text(code.read_text().replace(f"class {source}(", f"class {folder}("))
    meta = project / "components" / folder / "metadata.json"
    data = json.loads(meta.read_text())
    data["name"], data["nickname"] = folder, folder[:8]
    meta.write_text(json.dumps(data, indent=4))


def make_project(root):
    project = Path(root) / "project"
    (project / "components").mkdir(parents=True)
    shutil.copytree(EXAMPLE / "components" / A, project / "components" / A)
    shutil.copytree(EXAMPLE / "src", project / "src", ignore=shutil.ignore_patterns("__pycache__"))
    add_component(project, A, B)
    return project


def component_names(project):
    """{folder: component name}, as deploy keys what it embedded."""
    return {d.name: json.loads((d / "metadata.json").read_text())["name"]
            for d in sorted((project / "components").iterdir()) if d.is_dir()}


def png(rgb):
    """A valid 24 x 24 PNG of one colour: an icon edit the componentizer can still read."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\0" + bytes(rgb) * 24 for _ in range(24))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 24, 24, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


# --- what a developer does between two deploys -----------------------------------
# Each takes the project folder and returns it (a new one if it moved).


def edit_core(p):
    f = p / "src" / "ringkit" / "__init__.py"
    f.write_text(f.read_text().replace("z) for i in range(count)]", "z + 1.0) for i in range(count)]"))
    return p


def edit_code(p):
    f = p / "components" / A / "code.py"
    f.write_text(f.read_text().replace("            return None\n", "            return []\n"))
    return p


def revert_code(p):
    f = p / "components" / A / "code.py"
    f.write_text(f.read_text().replace("            return []\n", "            return None\n"))
    return p


def edit_comment(p):
    f = p / "components" / A / "code.py"
    f.write_text(f.read_text() + "# a comment, nothing else\n")
    return p


def edit_metadata(p):
    f = p / "components" / A / "metadata.json"
    data = json.loads(f.read_text())
    data["ghpython"]["inputParameters"][0]["description"] = "Circle radius, in metres"
    f.write_text(json.dumps(data, indent=4))
    return p


def edit_icon(p):
    (p / "components" / A / "icon.png").write_bytes(png((200, 40, 40)))
    return p


def add_third(p):
    add_component(p, A, "RingPointsThree")
    return p


def remove_b(p):
    shutil.rmtree(p / "components" / B)
    return p


def rename_b(p):
    add_component(p, B, "RingPointsRenamed")
    shutil.rmtree(p / "components" / B)
    return p


def move_project(p):
    moved = p.with_name("project-moved")
    p.rename(moved)
    return moved


def nothing(p):
    return p


UNINSTALL = "uninstall"   # a step: `dev.py uninstall` instead of an edit and a deploy
UPGRADE = "upgrade"       # a step: a newer ghuser-builder embeds a different check
FOREIGN_CORE = "foreign"  # before reload: Rhino has a module of the core's name from elsewhere (an installed .yak)


@dataclass
class Scenario:
    name: str
    steps: List[object]
    notes: Dict[str, str] = field(default_factory=dict)
    old: Dict[str, str] = field(default_factory=lambda: {A: "ran", B: "ran"})
    fresh: Dict[str, str] = field(default_factory=lambda: {A: "ran", B: "ran"})
    z: float = 0.0
    foreign_core: bool = False


SCENARIOS = [
    Scenario("rebuild, nothing changed", [nothing]),
    Scenario("core edit", [edit_core], z=1.0),
    Scenario("core edit, an installed .yak's core already loaded", [edit_core], z=1.0, foreign_core=True),
    Scenario("code.py edit", [edit_code], notes={A: "code.py changed"}, old={A: REPLACE, B: "ran"}),
    Scenario("code.py comment only", [edit_comment], notes={A: "code.py changed"}, old={A: REPLACE, B: "ran"}),
    Scenario("code.py edit, then reverted", [edit_code, revert_code], notes={A: "code.py changed"}),
    Scenario("metadata.json edit", [edit_metadata], notes={A: "restart Rhino, then replace"},
             old={A: RESTART, B: "ran"}),
    Scenario("icon.png edit", [edit_icon], notes={A: "restart Rhino, then replace"}, old={A: RESTART, B: "ran"}),
    Scenario("component added", [add_third], notes={"RingPointsThree": "new: restart Rhino"},
             fresh={A: "ran", B: "ran", "RingPointsThree": "ran"}),
    Scenario("component removed", [remove_b], notes={B: "removed"}, old={A: "ran", B: REMOVED}, fresh={A: "ran"}),
    Scenario("component renamed", [rename_b], notes={B: "removed", "RingPointsRenamed": "new"},
             old={A: "ran", B: REMOVED}, fresh={A: "ran", "RingPointsRenamed": "ran"}),
    # dist-dev/ moves along and the `# env:` path in every component changes; the old ones
    # name stamps and a src/ that are gone.
    Scenario("project moved", [move_project], notes={A: "code.py changed", B: "code.py changed"},
             old={A: GONE, B: GONE}),
    Scenario("ghuser-builder upgraded", [UPGRADE], notes={A: "code.py changed", B: "code.py changed"},
             old={A: REPLACE, B: REPLACE}),
    Scenario("dev.py uninstall", [UNINSTALL], old={A: GONE, B: GONE}, fresh={}),
]


def scenario_ids():
    return [s.name for s in SCENARIOS]


Step = Callable[[Path], Path]
