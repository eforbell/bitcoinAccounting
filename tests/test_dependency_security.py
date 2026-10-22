"""Guard the incident floor and the install path against accidental regressions."""

from pathlib import Path
import re
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_lock_pins_project_dependencies_and_safe_certifi() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    lock = (ROOT / "requirements.lock").read_text()
    pins = {}
    for line in lock.splitlines():
        if line.startswith("#") or not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)", line)
        assert match, f"unversioned or unsupported lock entry: {line}"
        pins[match[1].lower().replace("_", "-")] = match[2]

    assert len(pins) == len([line for line in lock.splitlines() if line and not line.startswith("#")])
    for requirement in project["dependencies"] + project["optional-dependencies"]["dev"]:
        name = re.split(r"[<>=!~\[]", requirement, maxsplit=1)[0]
        assert name.lower().replace("_", "-") in pins
    assert "certifi>=2026.10.19" in project["dependencies"]
    assert tuple(map(int, pins["certifi"].split("."))) >= (2026, 10, 19)


def test_deploy_bootstraps_pip_before_dependency_download() -> None:
    deploy = (ROOT / "deploy/deploy.sh").read_text()
    bootstrap = (ROOT / "scripts/ensure-safe-pip.sh").read_text()
    assert deploy.index("bash scripts/ensure-safe-pip.sh") < deploy.index("pip install -r requirements.lock")
    assert deploy.index("pip install -r requirements.lock") < deploy.index("pip install -e . --no-deps")
    assert "--upgrade pip" not in deploy
    assert "pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70" in bootstrap
