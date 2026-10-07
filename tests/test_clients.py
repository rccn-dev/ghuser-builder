"""Tests for clients/ against a fake GitLab API.   uv run --with pytest pytest tests"""

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

CLIENTS = Path(__file__).parents[1] / "clients"
PACKAGES = [  # newest first, as the API returns them with sort=desc
    {"id": 3, "name": "tool", "version": "1.2.0"},
    {"id": 2, "name": "tool", "version": "1.1.0"},
    {"id": 1, "name": "tool", "version": "1.0.0"},
]


class FakeGitLab(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.endswith("/packages"):
            per_page = int(self.path.split("per_page=")[1].split("&")[0])
            return self.json(PACKAGES[:per_page])
        if path.endswith("/package_files"):
            pid = int(path.split("/")[-2])
            version = next(p["version"] for p in PACKAGES if p["id"] == pid)
            return self.json([{"file_name": f"tool-{version}-rh8_0-any.yak"},
                              {"file_name": "Thing.ghuser"}])
        if "/packages/generic/" in path:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"PK fake yak")
            return
        self.send_response(404)
        self.end_headers()

    def json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def gitlab():
    server = HTTPServer(("127.0.0.1", 0), FakeGitLab)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def sync(gitlab, dest, keep):
    return subprocess.run(
        [sys.executable, str(CLIENTS / "sync_yak_feed.py"), "--gitlab", gitlab,
         "--project", "lab/tool", "--package", "tool", "--dest", str(dest), "--keep", str(keep)],
        capture_output=True, text=True, check=True).stdout


def test_sync_downloads_only_yak_files_of_the_newest_versions(gitlab, tmp_path):
    sync(gitlab, tmp_path, keep=2)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "tool-1.1.0-rh8_0-any.yak", "tool-1.2.0-rh8_0-any.yak"]


def test_sync_is_idempotent_and_prunes_old_versions(gitlab, tmp_path):
    sync(gitlab, tmp_path, keep=3)
    (tmp_path / "unrelated.yak").write_text("not ours")
    out = sync(gitlab, tmp_path, keep=1)
    assert "[new]" not in out
    assert sorted(p.name for p in tmp_path.iterdir()) == ["tool-1.2.0-rh8_0-any.yak", "unrelated.yak"]


def test_setup_lab_pip_never_prints_the_token():
    out = subprocess.run(
        [sys.executable, str(CLIENTS / "setup_lab_pip.py"), "--gitlab", "https://git.example",
         "--group-id", "12", "--token", "s3cret", "--dry-run"],
        capture_output=True, text=True, check=True).stdout
    assert "s3cret" not in out
    assert "https://<token>@git.example/api/v4/groups/12/-/packages/pypi/simple" in out
