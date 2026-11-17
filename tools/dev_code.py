"""A dev build's code.py: imports the core from a working copy instead of a package.

    python3 dev_code.py --env /abs/path/to/src components staged-components

Copies every component folder and prepends `# env: <path>` to its code.py, so Rhino
puts that folder on sys.path. A `# r:` pin on {{version}} names the same library,
which a dev build does not publish, so it is dropped. Used by `ghuser-build --env`
(in the image) and by local/ghuser_dev.py.
"""

import argparse
import os
import re
import shutil


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


def env_header(env):
    """The header line for an `# env:` path, exactly as given (it is a path on the user's machine)."""
    return f"# env: {env}\n" if env else ""


def bundles(src):
    return sorted(
        d for d in os.listdir(src)
        if os.path.isdir(os.path.join(src, d)) and d not in ("__pycache__", ".git")
    )


def stage(src, dst, env):
    """Copy the component folders in src to dst, with dev code.py files."""
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    for d in bundles(dst):
        path = os.path.join(dst, d, "code.py")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                text = dev_code(f.read(), env_header(env))
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True)
    ap.add_argument("src")
    ap.add_argument("dst")
    a = ap.parse_args()
    stage(a.src, a.dst, a.env)
