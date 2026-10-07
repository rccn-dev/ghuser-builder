"""Mirror released .yak files from GitLab into a folder Rhino uses as a package source.

    python sync_yak_feed.py --gitlab https://git.rccn.dev \\
        --project rccn/ringkit --package rccn-ringkit --dest "//lab-nas/rhino-packages"

Run it once by hand, or on a schedule on one machine that writes the lab's shared
folder (NAS, OneDrive, Syncthing). Each user adds that folder ONCE as a package
source in Rhino; after that, new releases appear in the Package Manager.

Downloads only what is missing and keeps the newest --keep versions. Standard
library only, so any Python 3.8+ runs it -- including Rhino 8's own.
For non-public projects pass a token (scope read_api) via --token or GITLAB_TOKEN.
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request


def api(base, path, token):
    req = urllib.request.Request(f"{base}/api/v4{path}")
    if token:
        req.add_header("PRIVATE-TOKEN", token)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def download(url, token, dest):
    req = urllib.request.Request(url)
    if token:
        req.add_header("PRIVATE-TOKEN", token)
    tmp = dest + ".part"
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as fh:
        while chunk := resp.read(1 << 16):
            fh.write(chunk)
    os.replace(tmp, dest)  # never leave a half-written .yak where Rhino can see it


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gitlab", required=True, help="e.g. https://git.rccn.dev")
    ap.add_argument("--project", required=True, help="path, e.g. rccn/ringkit")
    ap.add_argument("--package", required=True, help="generic package name (= GHUSER_YAK_NAME)")
    ap.add_argument("--dest", required=True, help="the package-source folder")
    ap.add_argument("--keep", type=int, default=3, help="versions to keep (default 3)")
    ap.add_argument("--token", default=os.environ.get("GITLAB_TOKEN"))
    a = ap.parse_args()

    base = a.gitlab.rstrip("/")
    pid = urllib.parse.quote(a.project, safe="")
    query = urllib.parse.urlencode({"package_type": "generic", "package_name": a.package,
                                    "order_by": "created_at", "sort": "desc", "per_page": a.keep})
    packages = [p for p in api(base, f"/projects/{pid}/packages?{query}", a.token)
                if p["name"] == a.package and "-dev." not in p["version"]]
    os.makedirs(a.dest, exist_ok=True)

    wanted = set()
    for pkg in packages[: a.keep]:
        for f in api(base, f"/projects/{pid}/packages/{pkg['id']}/package_files", a.token):
            name = f["file_name"]
            if not name.endswith(".yak"):
                continue
            wanted.add(name)
            target = os.path.join(a.dest, name)
            if os.path.exists(target):
                continue
            url = (f"{base}/api/v4/projects/{pid}/packages/generic/"
                   f"{urllib.parse.quote(a.package)}/{urllib.parse.quote(pkg['version'])}/{urllib.parse.quote(name)}")
            download(url, a.token, target)
            print(f"[new]     {name}")

    for name in sorted(os.listdir(a.dest)):
        if name.startswith(a.package + "-") and name.endswith(".yak") and name not in wanted:
            os.remove(os.path.join(a.dest, name))
            print(f"[removed] {name}")
    print(f"[ok]      {a.package}: {len(wanted)} version(s) in {a.dest}")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        sys.exit(f"GitLab answered {e.code} for {e.url} -- private project? pass --token / GITLAB_TOKEN")
