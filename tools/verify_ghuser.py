"""Check every built .ghuser against its source (runs inside the image).

    python3 verify_ghuser.py [--version V] [--prefix P] components build

Reads each file back with GH_IO.dll and compares name, description, parameter
counts and embedded code (after the componentizer's {{version}}, {{name}} and
{{ghuser_name}} substitutions) with components/<Folder>/. Exits 1 on any mismatch.
"""

import argparse
import base64
import json
import os
import sys

import clr

clr.AddReference("/opt/ghio/GH_IO")
import System  # noqa: E402
from GH_IO.Serialization import GH_LooseChunk  # noqa: E402


def load(path):
    root = GH_LooseChunk("UserObject")
    root.Deserialize_Binary(System.IO.File.ReadAllBytes(path))
    inner = GH_LooseChunk("UserObject")
    inner.Deserialize_Binary(root.GetByteArray("Object"))
    return root, inner


def count(chunk, name):
    return sum(1 for i in range(chunk.ChunkCount) if chunk.Chunks[i].Name == name)


def expected_code(code, version, name, ghuser_name):
    # Mirrors replace_templates() in the componentizer.
    if version:
        code = code.replace("{{version}}", version)
    return code.replace("{{name}}", name).replace("{{ghuser_name}}", ghuser_name)


def embedded_code(inner):
    # Rhino 8 script components store the code base64-encoded in Script/Text.
    return base64.b64decode(inner.FindChunk("Script").GetString("Text")).decode("utf-8")


def check(source_dir, build_dir, version, prefix):
    folder = os.path.basename(source_dir)
    meta = json.load(open(os.path.join(source_dir, "metadata.json"), encoding="utf-8"))
    code = open(os.path.join(source_dir, "code.py"), encoding="utf-8").read()
    ghuser = folder + ".ghuser"
    path = os.path.join(build_dir, ghuser)
    if not os.path.exists(path):
        return [f"{folder}: no {ghuser} was built"]

    root, inner = load(path)
    problems = []
    want_name = prefix + meta["name"]
    if root.GetString("Name") != want_name:
        problems.append(f"{folder}: name {root.GetString('Name')!r} != {want_name!r}")
    if root.GetString("Description") != meta.get("description", ""):
        problems.append(f"{folder}: description differs from metadata.json")
    if embedded_code(inner) != expected_code(code, version, meta["name"], ghuser):
        problems.append(f"{folder}: embedded code differs from code.py")

    params = inner.FindChunk("ParameterData")
    gh = meta.get("ghpython", {})
    for kind, key in (("InputParam", "inputParameters"), ("OutputParam", "outputParameters")):
        want, got = len(gh.get(key, [])), count(params, kind)
        if want != got:
            problems.append(f"{folder}: {got} {kind}s, metadata.json declares {want}")
    return problems


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--version", default=None)
    ap.add_argument("--prefix", default="")
    a = ap.parse_args()

    bundles = sorted(
        d for d in os.listdir(a.src)
        if os.path.isdir(os.path.join(a.src, d)) and d not in ("__pycache__", ".git")
    )
    if not bundles:
        print(f"[FAILED]   no component folders in {a.src}")
        sys.exit(1)
    problems = [p for d in bundles for p in check(os.path.join(a.src, d), a.out, a.version, a.prefix)]
    for d in bundles:
        if not any(p.startswith(d + ":") for p in problems):
            print(f"[verified] {d}.ghuser")
    for p in problems:
        print(f"[FAILED]   {p}")
    sys.exit(1 if problems else 0)
