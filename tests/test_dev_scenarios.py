"""The dev loop, scenario by scenario (tests/scenarios.py), on a headless canvas (tests/canvas.py).

    uv run --no-project --with pytest pytest tests/test_dev_scenarios.py

Builds with a stand-in for the componentizer by default: everything else is the real
ghuser_dev.build, staging, stamps and RELOAD. With GHUSER_TEST_IMAGE=<builder image>
each scenario also builds for real, through the tar stream into Docker, and the image
verifies that every .ghuser embeds exactly the code run here.
"""

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "local"))
sys.path.insert(0, str(Path(__file__).parent))
import ghuser_dev  # noqa: E402
from canvas import Canvas  # noqa: E402
from scenarios import (  # noqa: E402
    A, SCENARIOS, UNINSTALL, UPGRADE, component_names, edit_code, make_project, scenario_ids,
)

IMAGE = os.environ.get("GHUSER_TEST_IMAGE")


def fake_componentizer(staged, built, prefix, image):
    os.makedirs(built)
    for d in ghuser_dev.bundles(staged):
        Path(built, d + ".ghuser").write_text("stand-in")


@pytest.fixture(params=["fake", "docker"])
def deploy(request, monkeypatch, capsys):
    """deploy(project) -> ({component name: embedded code}, {folder: note}): ghuser_dev.build."""
    if request.param == "fake":
        monkeypatch.setattr(ghuser_dev, "build_with_docker", fake_componentizer)
    elif not IMAGE:
        pytest.skip("set GHUSER_TEST_IMAGE to build in Docker")

    def run(project):
        capsys.readouterr()
        embedded = ghuser_dev.build(str(project / "components"), str(project / "dist-dev"),
                                    str(project / "src"), "", "docker", IMAGE)
        out = capsys.readouterr().out
        notes = dict(re.findall(r"^ghuser_dev: (\w+) (new.*|removed.*|code\.py changed.*|inputs.*)$", out, re.M))
        return embedded, notes
    return run


def first_z(run):
    return run.value[0].Z


@pytest.mark.parametrize("scenario", SCENARIOS, ids=scenario_ids())
def test_scenario(scenario, deploy, tmp_path, monkeypatch):
    monkeypatch.setenv("GHUSER_USEROBJECTS", str(tmp_path / "UserObjects"))
    project = make_project(tmp_path)
    before = component_names(project)
    embedded, _ = deploy(project)
    stamps = ghuser_dev.stamps_path(project / "dist-dev")

    with Canvas() as canvas:
        placed = {f: canvas.place(embedded[name], name) for f, name in before.items()}
        for f, c in placed.items():
            run = c.solve(1.0, 4, 0.0)
            assert run.outcome == "ran" and first_z(run) == 0.0, (f, run)
        if scenario.foreign_core:
            installed = tmp_path / "installed"
            (installed / "ringkit").mkdir(parents=True)
            (installed / "ringkit" / "__init__.py").write_text(
                "def ring_points(radius, count, z=0.0):\n    return [(radius, 0.0, 99.0)] * count\n")
            canvas.import_foreign(installed, "ringkit")

        notes = {}
        for step in scenario.steps:
            if step == UNINSTALL:
                ghuser_dev.uninstall(str(project / "dist-dev"), str(tmp_path / "UserObjects"))
                embedded, notes = {}, {}
                continue
            if step == UPGRADE:
                monkeypatch.setattr(ghuser_dev.staging, "STALE_CHECK",
                                    ghuser_dev.staging.STALE_CHECK.replace("# ghuser-dev: stops", "# ghuser-dev 9: stops"))
            else:
                project = step(project)
            embedded, notes = deploy(project)

        assert set(notes) == set(scenario.notes), notes
        for f, want in scenario.notes.items():
            assert want in notes[f], (f, notes[f])

        # deploy reloads a running Rhino (uninstall too), then the file is closed and opened again.
        env = project / "src" if embedded else None
        report = canvas.reload(env, embedded, stamps)
        if scenario.foreign_core:
            assert report["elsewhere"] and report["elsewhere"][0].startswith("ringkit from ")
        for when in ("after reload", "reopened"):
            if when == "reopened":
                canvas.reopen()
            for f, want in scenario.old.items():
                run = placed[f].solve(1.0, 4, 0.0)
                assert run.outcome == want, (when, f, run)
                if want == "ran":
                    assert first_z(run) == scenario.z, (when, f)
                elif run.state == "stopped":
                    assert run.error.startswith("ghuser-dev: "), run

        now = component_names(project) if embedded else {}
        assert set(scenario.fresh) == set(now)
        for f, want in scenario.fresh.items():
            run = canvas.place(embedded[now[f]], now[f]).solve(1.0, 4, 0.0)
            assert run.outcome == want and first_z(run) == scenario.z, (f, run)


def test_reload_names_the_components_it_stops(deploy, tmp_path, monkeypatch):
    """deploy's report: what it recomputed and what it stopped, as it prints them."""
    monkeypatch.setenv("GHUSER_USEROBJECTS", str(tmp_path / "UserObjects"))
    project = make_project(tmp_path)
    embedded, _ = deploy(project)
    names = component_names(project)
    with Canvas() as canvas:
        for name in names.values():
            canvas.place(embedded[name], name)
        edit_code(project)
        embedded, _ = deploy(project)
        report = canvas.reload(project / "src", embedded, ghuser_dev.stamps_path(project / "dist-dev"))
    assert report["error"] is None
    assert report["stale"] == [names[A]]
    assert report["recomputed"] == [n for f, n in names.items() if f != A]
    assert "ringkit" in report["dropped"]


@pytest.mark.skipif(not IMAGE, reason="set GHUSER_TEST_IMAGE to build in Docker")
def test_quick_edits_build_what_is_on_disk(tmp_path, capsys):
    """Each build sees the edit just made: colima's sshfs once served the previous file."""
    project = make_project(tmp_path)
    code = project / "components" / A / "code.py"
    for i in range(1, 6):
        code.write_text(code.read_text() + "#" + "x" * (37 * i) + "\n")
        embedded = ghuser_dev.build(str(project / "components"), str(project / "dist-dev"),
                                    str(project / "src"), "", "docker", IMAGE)
        assert embedded[component_names(project)[A]].endswith("#" + "x" * (37 * i) + "\n" + ghuser_dev.staging.STALE_STOP)
        assert "[verified]" in capsys.readouterr().out


@pytest.mark.skipif(not IMAGE, reason="set GHUSER_TEST_IMAGE to build in Docker")
def test_a_failed_build_leaves_the_last_good_one(tmp_path, capsys):
    project = make_project(tmp_path)
    ghuser_dev.build(str(project / "components"), str(project / "dist-dev"), str(project / "src"), "", "docker", IMAGE)
    good = sorted(p.name for p in (project / "dist-dev").iterdir())
    stamps = (project / "dist-dev" / ghuser_dev.STAMPS).read_text()
    (project / "components" / A / "metadata.json").write_text("{ not json")
    with pytest.raises(SystemExit):
        ghuser_dev.build(str(project / "components"), str(project / "dist-dev"), str(project / "src"), "", "docker", IMAGE)
    assert sorted(p.name for p in (project / "dist-dev").iterdir()) == good
    assert (project / "dist-dev" / ghuser_dev.STAMPS).read_text() == stamps


