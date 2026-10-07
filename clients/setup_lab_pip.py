"""Point pip on this machine at the lab's GitLab package registry (run once per user).

    python setup_lab_pip.py --gitlab https://git.rccn.dev --group-id 12
    python setup_lab_pip.py --gitlab https://git.rccn.dev --group-id 12 --token <deploy-token>  # internal group

Writes the per-user pip config file that pip -- including the pip Rhino 8 uses for
`# r:` requirement lines -- reads, setting index-url to the group's PyPI endpoint:

    https://git.rccn.dev/api/v4/groups/<id>/-/packages/pypi/simple

index-url (not extra-index-url) on purpose: with an extra index, a package of the
same name on pypi.org could win (dependency confusion). GitLab forwards names it
does not have to pypi.org, so public dependencies such as compas still resolve --
as long as the instance setting "Forward PyPI package requests" is on (the default).

A token is only needed when the group is not public. Use a GROUP DEPLOY TOKEN with
the single scope read_package_registry, rotate it each semester, and never a
personal access token: it ends up in a plain-text file on every lab machine.
"""

import argparse
import configparser
import os
import platform
import sys
import urllib.parse


def config_path():
    if platform.system() == "Windows":
        return os.path.join(os.environ["APPDATA"], "pip", "pip.ini")
    if platform.system() == "Darwin":
        return os.path.expanduser("~/Library/Application Support/pip/pip.conf")
    return os.path.expanduser("~/.config/pip/pip.conf")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gitlab", required=True)
    ap.add_argument("--group-id", required=True, help="numeric id of the GitLab group")
    ap.add_argument("--token", help="group deploy token (read_package_registry)")
    ap.add_argument("--token-name", default="lab-pip", help="the deploy token's username")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    host = urllib.parse.urlsplit(a.gitlab.rstrip("/"))
    auth = f"{urllib.parse.quote(a.token_name)}:{urllib.parse.quote(a.token)}@" if a.token else ""
    index = f"{host.scheme}://{auth}{host.netloc}/api/v4/groups/{a.group_id}/-/packages/pypi/simple"

    path = config_path()
    cfg = configparser.ConfigParser()
    cfg.read(path)
    if not cfg.has_section("global"):
        cfg.add_section("global")
    previous = cfg.get("global", "index-url", fallback=None)
    cfg.set("global", "index-url", index)

    shown = index.replace(auth, "<token>@") if auth else index
    if a.dry_run:
        print(f"would set index-url = {shown}\n in {path}")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        cfg.write(fh)
    print(f"[ok] index-url = {shown}\n     in {path}")
    if previous and previous != index:
        print(f"[!]  replaced a previous index-url: {previous}")


if __name__ == "__main__":
    sys.exit(main())
