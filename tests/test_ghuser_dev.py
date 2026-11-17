"""Tests for local/ghuser_dev.py that need no Rhino.   uv run --with pytest pytest tests"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "local"))
import ghuser_dev  # noqa: E402

RING_POINTS = '''"""Ring Points."""
# r: ringkit=={{version}}

import Rhino.Geometry as rg
from ghpythonlib.componentbase import executingcomponent as component


class RingPoints(component):
    def RunScript(self, radius):
        import json
        from ringkit import ring_points
        return ring_points(radius)
'''


def test_dev_code_adds_the_header_and_drops_the_version_pin():
    code = ghuser_dev.dev_code(RING_POINTS, "# env: /src\n")
    assert code.startswith("# env: /src\n")
    assert "{{version}}" not in code
    assert "import Rhino.Geometry" in code


def test_dev_code_keeps_other_requirements_and_changes_nothing_without_env():
    code = "# r: ringkit=={{version}}, numpy>=1,<2\nx = 1\n"
    assert ghuser_dev.dev_code(code, "# env: /src\n") == "# env: /src\n# r: numpy>=1,<2\nx = 1\n"
    assert ghuser_dev.dev_code(code, "") == code


def test_requirements_split_on_names_not_on_version_commas():
    assert ghuser_dev.requirements("# r: numpy>=1,<2, scipy\n#r:  matplotlib\n") == ["numpy>=1,<2", "scipy", "matplotlib"]


def test_imported_modules_finds_imports_inside_functions_and_skips_rhino_and_stdlib():
    assert ghuser_dev.imported_modules(RING_POINTS) == ["ringkit"]


@pytest.fixture
def uo(tmp_path, monkeypatch):
    monkeypatch.setenv("GHUSER_BACKUPS", str(tmp_path / "backups"))
    folder = tmp_path / "UserObjects"
    folder.mkdir()
    return folder


@pytest.fixture
def out(tmp_path):
    folder = tmp_path / "checkout" / "build" / "ghuser-dev"
    folder.mkdir(parents=True)
    for name in ("A.ghuser", "B.ghuser"):
        (folder / name).write_text("new")
    return folder


def test_link_backs_up_loose_copies_and_only_warns_about_other_checkouts(tmp_path, uo, out):
    (uo / "old").mkdir()
    (uo / "old" / "A.ghuser").write_text("old")
    (uo / "Unrelated.ghuser").write_text("keep")
    other = tmp_path / "other"
    other.mkdir()
    (other / "B.ghuser").write_text("theirs")
    (uo / "someone-dev").symlink_to(other)

    notes = ghuser_dev.link(str(out), "tool-dev", str(uo))

    assert os.path.realpath(uo / "tool-dev") == os.path.realpath(out)
    assert not (uo / "old").exists()  # emptied, so removed
    assert (uo / "Unrelated.ghuser").exists()
    assert (other / "B.ghuser").read_text() == "theirs"
    backups = list((tmp_path / "backups").iterdir())
    assert (backups[0] / "old" / "A.ghuser").read_text() == "old"
    assert any("WARNING B.ghuser" in n for n in notes)


def test_link_again_is_quiet_and_moves_a_renamed_link(uo, out):
    ghuser_dev.link(str(out), "tool-dev", str(uo))
    assert ghuser_dev.link(str(out), "tool-dev", str(uo)) == []
    notes = ghuser_dev.link(str(out), "renamed-dev", str(uo))
    assert ghuser_dev.links_to(str(out), str(uo)) == ["renamed-dev"]
    assert notes == ["removed the older link tool-dev"]


def test_link_repoints_a_link_to_another_checkout(tmp_path, uo, out):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (uo / "tool-dev").symlink_to(elsewhere)
    notes = ghuser_dev.link(str(out), "tool-dev", str(uo))
    assert os.path.realpath(uo / "tool-dev") == os.path.realpath(out)
    assert "pointed at" in notes[0]


def test_status_reports_duplicates_and_broken_links_then_uninstall(tmp_path, uo, out, capsys):
    assert ghuser_dev.status(str(out), str(uo)) == [f"{out} is not linked into Grasshopper; run deploy"]
    ghuser_dev.link(str(out), "tool-dev", str(uo))
    assert ghuser_dev.status(str(out), str(uo)) == []
    (uo / "gone-dev").symlink_to(tmp_path / "gone")
    (uo / "A.ghuser").write_text("copied by hand")
    problems = ghuser_dev.status(str(out), str(uo))
    assert any(p.startswith("gone-dev is a link") for p in problems)
    assert any(p.startswith("A.ghuser loads 2 times") for p in problems)

    ghuser_dev.uninstall(str(out), str(uo))
    assert not (uo / "tool-dev").exists()
    assert out.is_dir()


def test_the_original_command_line_still_means_build(monkeypatch):
    seen = {}
    monkeypatch.setattr(ghuser_dev, "build", lambda src, out, env, *rest: seen.update(src=src, out=out, env=env))
    ghuser_dev.main(["components", "dist-dev", "--env", "src"])
    assert seen == {"src": "components", "out": "dist-dev", "env": "src"}


def test_docker_command_mounts_the_current_folder_and_passes_the_host_env_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cmd = ghuser_dev.docker_command("components", str(tmp_path / ".stage"), "/home/me/proj/src", "", "img:1")
    assert cmd[:6] == ["docker", "run", "--rm", "-v", f"{tmp_path}:/work", "-w"]
    i = cmd.index("img:1")
    assert cmd[i:] == ["img:1", "ghuser-build", "--version", ghuser_dev.VERSION,
                       "--env", "/home/me/proj/src", "components", ".stage"]


def test_docker_command_refuses_folders_outside_the_mount(tmp_path, monkeypatch):
    (tmp_path / "proj").mkdir()
    monkeypatch.chdir(tmp_path / "proj")
    with pytest.raises(SystemExit):
        ghuser_dev.docker_command("../components", "dist-dev", None, "", "img:1")


def test_a_folder_is_not_a_link_and_a_symlink_is(tmp_path, out):
    (tmp_path / "plain").mkdir()
    (tmp_path / "link").symlink_to(out)
    assert not ghuser_dev.is_link(str(tmp_path / "plain"))
    assert ghuser_dev.is_link(str(tmp_path / "link"))
    assert not ghuser_dev.is_link(str(tmp_path / "missing"))


def test_status_names_components_an_installed_package_also_carries(tmp_path, uo, out, monkeypatch):
    pk = tmp_path / "packages" / "my-tool" / "1.0.0"
    pk.mkdir(parents=True)
    (pk / "A.ghuser").write_text("released")
    monkeypatch.setenv("GHUSER_PACKAGES", str(tmp_path / "packages"))
    ghuser_dev.link(str(out), "tool-dev", str(uo))
    problems = ghuser_dev.status(str(out), str(uo))
    assert len(problems) == 1 and problems[0].startswith("A.ghuser is also in an installed package")
