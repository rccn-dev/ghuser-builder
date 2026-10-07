"""Package built .ghuser files as a Rhino package (.yak), without the yak CLI.

    python3 make_yak.py --name NAME --version X.Y.Z
                        [--manifest yak.json] [--include SRC:DST ...] ghuser_dir out_dir

A .yak is a zip archive with a manifest.yml at its root. McNeel's `yak build`
only ships for Windows and macOS, so this writes the same layout directly:

    manifest.yml
    icon.png              (if the manifest names one)
    *.ghuser              Grasshopper loads user objects from the package root
    <DST>/...             anything passed with --include (e.g. a vendored core: lib/)

The file is named NAME-VERSION-rh8_0-any.yak: the distribution tag says Rhino 8
(script components with CPython need it) on any platform.

yak.json (optional) holds the human fields of manifest.yml:
    {"authors": ["..."], "description": "...", "url": "...", "keywords": ["..."], "icon": "icon.png"}
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile

SEMVER = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
DISTRIBUTION = "rh8_0-any"


def yaml_scalar(value):
    return json.dumps(str(value), ensure_ascii=False)  # a JSON string is a valid YAML scalar


def manifest_yml(name, version, fields):
    lines = [f"name: {name}", f"version: {version}"]
    authors = fields.get("authors") or ["unknown"]
    lines.append("authors:")
    lines += [f"- {yaml_scalar(a)}" for a in authors]
    lines.append(f"description: {yaml_scalar(fields.get('description', name))}")
    if fields.get("url"):
        lines.append(f"url: {yaml_scalar(fields['url'])}")
    if fields.get("keywords"):
        lines.append("keywords:")
        lines += [f"- {yaml_scalar(k)}" for k in fields["keywords"]]
    if fields.get("icon"):
        lines.append(f"icon: {os.path.basename(fields['icon'])}")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ghuser_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--name", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--manifest")
    ap.add_argument("--include", action="append", default=[], metavar="SRC:DST")
    a = ap.parse_args()

    if not NAME.match(a.name):
        sys.exit(f"make_yak: package name {a.name!r} must be letters, digits, '-' or '_'")
    if not SEMVER.match(a.version):
        sys.exit(f"make_yak: version {a.version!r} is not semantic (X.Y.Z[-pre])")
    fields = json.load(open(a.manifest, encoding="utf-8")) if a.manifest else {}

    ghusers = sorted(f for f in os.listdir(a.ghuser_dir) if f.endswith(".ghuser"))
    if not ghusers:
        sys.exit(f"make_yak: no .ghuser files in {a.ghuser_dir}")

    with tempfile.TemporaryDirectory() as stage:
        for f in ghusers:
            shutil.copy2(os.path.join(a.ghuser_dir, f), stage)
        if fields.get("icon"):
            icon_src = os.path.join(os.path.dirname(a.manifest), fields["icon"])
            shutil.copy2(icon_src, os.path.join(stage, os.path.basename(fields["icon"])))
        for spec in a.include:
            src, _, dst = spec.partition(":")
            dst = dst or os.path.basename(src.rstrip("/"))
            target = os.path.join(stage, dst)
            if os.path.isdir(src):
                shutil.copytree(src, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                os.makedirs(os.path.dirname(target) or stage, exist_ok=True)
                shutil.copy2(src, target)
        with open(os.path.join(stage, "manifest.yml"), "w", encoding="utf-8") as fh:
            fh.write(manifest_yml(a.name, a.version, fields))

        out = os.path.join(a.out_dir, f"{a.name}-{a.version}-{DISTRIBUTION}.yak")
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for folder, _, files in os.walk(stage):
                for f in sorted(files):
                    full = os.path.join(folder, f)
                    z.write(full, os.path.relpath(full, stage))
    print(f"[packaged] {os.path.basename(out)}  ({len(ghusers)} components)")


if __name__ == "__main__":
    main()
