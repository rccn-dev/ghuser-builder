"""Run ghuser-build on this machine, in the same image CI uses. Any OS with Docker.

Copy into a project (e.g. scripts/ghuser.py) and run from the project root:

    uv run scripts/ghuser.py                         # components/ -> dist/, dev version
    uv run scripts/ghuser.py --yak my-tool           # ...and a .yak
    GHUSER_VERSION=1.2.3 uv run scripts/ghuser.py --yak my-tool

The same as the bash script beside it, for Windows. Any ghuser-build option passes
through. Needs Docker (Desktop, OrbStack, colima); without the image, build it once:
    docker build -t ghuser-builder:local <ghuser-builder checkout or git URL>
"""

import os
import subprocess
import sys

IMAGE = os.environ.get("GHUSER_BUILDER_IMAGE", "ghuser-builder:local")
PASS = ("GHUSER_VERSION", "GHUSER_PREFIX", "GHUSER_YAK_NAME", "GHUSER_YAK_INCLUDE")

cmd = ["docker", "run", "--rm", "-v", f"{os.getcwd()}:/work", "-w", "/work", "-e", "HOME=/tmp"]
if hasattr(os, "getuid"):  # files in the mount belong to you, not root (not on Windows)
    cmd += ["-u", f"{os.getuid()}:{os.getgid()}"]
for name in PASS:
    cmd += ["-e", name]
cmd += [IMAGE, "ghuser-build", *sys.argv[1:],
        os.environ.get("GHUSER_COMPONENTS", "components"), os.environ.get("GHUSER_OUT", "dist")]
try:
    sys.exit(subprocess.run(cmd).returncode)
except FileNotFoundError:
    sys.exit("ghuser: docker not found; install Docker Desktop (or OrbStack, colima) and start it")
