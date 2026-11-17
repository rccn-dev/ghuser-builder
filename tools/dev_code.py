"""A dev build's code.py: imports the core from a working copy instead of a package.

    python3 dev_code.py --env /abs/path/to/src components staged-components

Copies every component folder and prepends `# env: <path>` to its code.py, so Rhino
puts that folder on sys.path. A `# r:` pin on {{version}} names the same library,
which a dev build does not publish, so it is dropped. Used by `ghuser-build --env`
(in the image) and by local/ghuser_dev.py.

local/ghuser_dev.py also passes `stamps`: each component then carries a fingerprint
of its code.py, metadata.json and icon.png, and stops with an error when the latest
dev build (the stamps file) has a different one. A component on the canvas keeps
the code it was placed with, so this is how an old one in a reopened file shows itself.
"""

import argparse
import hashlib
import os
import re
import shutil


def split_requirements(line):
    """`numpy>=1,<2, scipy` -> ['numpy>=1,<2', 'scipy']: a comma starts a new one only before a name."""
    return [r.strip() for r in re.split(r",\s*(?=[A-Za-z])", line) if r.strip()]


def dev_code(code, header, check=""):
    """code.py as a dev build embeds it: the `# env:` header, and with it no `# r:` pin on {{version}}."""
    if not header:
        return check + code
    lines = []
    for line in code.splitlines(keepends=True):
        m = re.match(r"#\s*r\s*:(.*)$", line.rstrip("\r\n"))
        if m and "{{version}}" in m.group(1):
            kept = [r for r in split_requirements(m.group(1)) if "{{version}}" not in r]
            if not kept:
                continue
            line = "# r: " + ", ".join(kept) + "\n"
        lines.append(line)
    return header + check + "".join(lines)


def env_header(env):
    """The header line for an `# env:` path, exactly as given (it is a path on the user's machine)."""
    return f"# env: {env}\n" if env else ""


STALE_CHECK = '''# ghuser-dev: stops this component when the latest dev build has different code or parameters
def _ghuser_dev_check(stamps, folder, code, interface):
    import json
    try:
        with open(stamps, encoding="utf-8") as f:
            latest = json.load(f).get(folder)
    except (OSError, ValueError):
        return "dev: not deployed", "its dev build is no longer deployed; replace it from the installed package"
    if latest is None:
        return "dev: removed", folder + " is not in the latest dev build (removed or renamed)"
    if latest["interface"] != interface:
        return "dev: restart, replace", ("inputs, outputs or icon changed in the latest dev build;"
                                         " restart Rhino, then replace this component")
    if latest["code"] != code:
        return "dev: replace", "code.py changed in the latest dev build; replace this component from the toolbar"
    return None


_ghuser_dev_stale = _ghuser_dev_check(%r, %r, %r, %r)
if "ghenv" in globals():
    if _ghuser_dev_stale:
        ghenv.Component.Message = _ghuser_dev_stale[0]
    elif (ghenv.Component.Message or "").startswith("dev: "):
        ghenv.Component.Message = ""
del _ghuser_dev_check
'''

# Appended: a stale component's RunScript raises, which Rhino shows on the component
# (an error at the top would show only "Error getting GH_ScriptInstance instance").
STALE_STOP = '''

# ghuser-dev: a stale component stops here, with the reason on the canvas
if _ghuser_dev_stale:
    for _ghuser_dev_class in [v for v in list(globals().values()) if isinstance(v, type) and "RunScript" in vars(v)]:
        def _ghuser_dev_stopped(*args, **kwargs):
            raise RuntimeError("ghuser-dev: " + _ghuser_dev_stale[1])
        _ghuser_dev_class.RunScript = _ghuser_dev_stopped
'''


def fingerprint(code, folder):
    """{code, interface}: what the canvas copy carries, and what Grasshopper reads only at startup."""
    def digest(*parts):
        h = hashlib.sha256()
        for part in parts:
            h.update(len(part).to_bytes(8, "big") + part)
        return h.hexdigest()[:16]

    def read(name):
        path = os.path.join(folder, name)
        return open(path, "rb").read() if os.path.isfile(path) else b""

    # The check itself counts as code: a newer ghuser-builder changes what is embedded.
    return {"code": digest(code.encode("utf-8"), (STALE_CHECK + STALE_STOP).encode("utf-8")),
            "interface": digest(read("metadata.json"), read("icon.png"))}


def bundles(src):
    return sorted(
        d for d in os.listdir(src)
        if os.path.isdir(os.path.join(src, d)) and d not in ("__pycache__", ".git")
    )


def stage(src, dst, env, stamps=None):
    """Copy the component folders in src to dst, with dev code.py files.

    With stamps (the absolute path of the stamps file), every component also gets
    the stale check. Returns {folder: fingerprint}, for the stamps file.
    """
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    prints = {}
    for d in bundles(dst):
        path = os.path.join(dst, d, "code.py")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                code = f.read()
            text = dev_code(code, env_header(env))
            if stamps:
                prints[d] = fingerprint(text, os.path.join(dst, d))
                check = STALE_CHECK % (stamps, d, prints[d]["code"], prints[d]["interface"])
                text = dev_code(code, env_header(env), check) + STALE_STOP
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
    return prints


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True)
    ap.add_argument("src")
    ap.add_argument("dst")
    a = ap.parse_args()
    stage(a.src, a.dst, a.env)
