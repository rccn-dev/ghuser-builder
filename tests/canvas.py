"""A headless stand-in for Grasshopper's canvas: enough to run a dev build's components.

It does what Rhino 8 does with a script component, as far as the dev loop depends on it
(tests/rhino/run_scenarios.py checks the same scenarios in a real Rhino):
  * a placed component keeps the code it was placed with, and writes type hints into
    RunScript's signature;
  * compiling (placing, opening a file, SetSource) puts `# env:` paths on sys.path and
    runs the top level, with `ghenv` defined; solving calls RunScript;
  * local/ghuser_dev.py's RELOAD script runs against it unchanged, through stubs of the
    Grasshopper and GH_IO objects it touches.
Not modelled: the toolbar (Grasshopper reads user objects only at startup), icons, .ghuser files.
"""

import base64
import json
import os
import re
import sys
import tempfile
import types


class Point3d:
    def __init__(self, x, y, z):
        self.X, self.Y, self.Z = x, y, z


class _Component:  # ghpythonlib.componentbase.executingcomponent
    pass


class Run:
    """What one solve did: state is "ran", "stopped" (by the dev check) or "failed"."""

    def __init__(self, state, label="", value=None, error=""):
        self.state, self.label, self.value, self.error = state, label, value, error

    @property
    def outcome(self):
        """"ran", or the label it stopped with: what a scenario expects."""
        return "ran" if self.state == "ran" else (self.label or self.state)

    def __repr__(self):
        return f"Run({self.state!r}, label={self.label!r}, error={self.error!r})"


class PlacedComponent:
    """A script component on the canvas: its own copy of the code, compiled on demand."""

    def __init__(self, code, name):
        self.Name = self.NickName = name
        self.Message = ""
        self.code = self._with_type_hints(code)
        self.cls = None
        self.error = ""

    @staticmethod
    def _with_type_hints(code):
        # Rhino writes the inputs' type hints into the signature when a component is placed.
        return re.sub(r"def RunScript\(self, ([^)]*)\)",
                      lambda m: "def RunScript(self, " + ", ".join(a.strip() + ": float" for a in m.group(1).split(",")) + ")",
                      code)

    def compile(self):
        for line in self.code.splitlines():
            m = re.match(r"#\s*env\s*:\s*(.+)$", line)
            if m and m.group(1).strip() not in sys.path:
                sys.path.insert(0, m.group(1).strip())
        scope = {"__name__": "__main__", "ghenv": types.SimpleNamespace(Component=self)}
        self.cls, self.error = None, ""
        try:
            exec(compile(self.code, self.Name, "exec"), scope)
        except Exception as e:  # Rhino: "Error getting GH_ScriptInstance instance"
            self.error = f"{type(e).__name__}: {e}"
            return
        self.cls = next(v for v in scope.values() if isinstance(v, type) and "RunScript" in vars(v))

    def solve(self, *inputs):
        if self.cls is None:
            return Run("failed", self.Message, error=self.error)
        try:
            value = self.cls().RunScript(*inputs)
        except RuntimeError as e:
            if str(e).startswith("ghuser-dev: "):
                return Run("stopped", self.Message, error=str(e))
            return Run("failed", self.Message, error=str(e))
        except Exception as e:
            return Run("failed", self.Message, error=f"{type(e).__name__}: {e}")
        return Run("ran", self.Message, value=value)

    # What RELOAD calls on a Grasshopper object.
    def Write(self, chunk):
        chunk.text = base64.b64encode(self.code.encode("utf-8")).decode("ascii")

    def TryGetSource(self):
        return True, self.code

    def SetSource(self, source):
        self.code = source
        self.compile()

    def ExpireSolution(self, recompute):
        pass


class _Chunk:  # GH_IO.Serialization.GH_LooseChunk, as RELOAD reads it
    def __init__(self, name):
        self.text = None

    def FindChunk(self, name):
        return self if name == "Script" and self.text is not None else None

    def GetString(self, name):
        return self.text


class Canvas:
    """One Grasshopper document in one Rhino session. Use as a context manager: it puts the
    Rhino stubs in sys.modules and takes them, and every module the session imported, back out."""

    def __init__(self):
        self.objects = []

    def __enter__(self):
        self._modules, self._path = set(sys.modules), list(sys.path)
        rhino = types.ModuleType("Rhino")
        rhino.Geometry = types.SimpleNamespace(Point3d=Point3d)
        gh = types.ModuleType("Grasshopper")
        document = types.SimpleNamespace(Objects=self.objects, NewSolution=lambda expire: None)
        gh.Instances = types.SimpleNamespace(ActiveCanvas=types.SimpleNamespace(Document=document))
        stubs = {
            "Rhino": rhino, "Rhino.Geometry": rhino.Geometry,
            "ghpythonlib": types.ModuleType("ghpythonlib"),
            "ghpythonlib.componentbase": types.SimpleNamespace(executingcomponent=_Component),
            "Grasshopper": gh,
            "GH_IO": types.ModuleType("GH_IO"),
            "GH_IO.Serialization": types.SimpleNamespace(GH_LooseChunk=_Chunk),
        }
        sys.modules.update(stubs)
        return self

    def __exit__(self, *exc):
        for name in set(sys.modules) - self._modules:
            del sys.modules[name]
        sys.path[:] = self._path

    def place(self, code, name):
        obj = PlacedComponent(code, name)
        obj.compile()
        self.objects.append(obj)
        return obj

    def reopen(self):
        """Close and open the document: every component compiles again from the code it carries."""
        for obj in self.objects:
            obj.compile()

    def reload(self, env, embedded, stamps):
        """What `deploy` (and `uninstall`) does to a running Rhino: ghuser_dev.RELOAD, run here. Returns its report."""
        import ghuser_dev

        with tempfile.TemporaryDirectory() as tmp:
            report = os.path.join(tmp, "report.json")
            script = ghuser_dev.RELOAD % (os.path.realpath(env) if env else None, embedded, stamps, report)
            exec(compile(script, "reload.py", "exec"), {"__name__": "__main__"})
            with open(report) as f:
                return json.load(f)

    def import_foreign(self, folder, module):
        """Rhino imported `module` from folder earlier in this session (an installed .yak's core)."""
        for name in [n for n in sys.modules if n == module or n.startswith(module + ".")]:
            del sys.modules[name]
        sys.path.insert(0, str(folder))
        __import__(module)
        sys.path.remove(str(folder))
