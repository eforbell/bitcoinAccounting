"""Guard the incident floor and the install path against accidental regressions."""

from pathlib import Path
import re
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_lock_pins_project_dependencies_and_safe_certifi() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    lock = (ROOT / "requirements.lock").read_text()
    below, from_311 = 'python_version < "3.11"', 'python_version >= "3.11"'
    pins: dict[str, dict[str | None, str]] = {}
    for line in lock.splitlines():
        if line.startswith("#") or not line:
            continue
        pin, *marker = line.split(";", 1)
        condition = marker[0].strip() if marker else None
        assert condition in (None, below, from_311), f"unsupported marker: {line}"
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)", pin.strip())
        assert match, f"unversioned or unsupported lock entry: {line}"
        pins.setdefault(match[1].lower().replace("_", "-"), {})[condition] = match[2]

    assert sum(map(len, pins.values())) == len([line for line in lock.splitlines() if line and not line.startswith("#")])
    # A package pinned per Python version (no single release has wheels for 3.10 and 3.14) covers both.
    for name, versions in pins.items():
        if from_311 in versions:
            assert set(versions) == {below, from_311}, f"{name} must be pinned for both sides of 3.11"
    for requirement in project["dependencies"] + project["optional-dependencies"]["dev"]:
        name = re.split(r"[<>=!~\[]", requirement, maxsplit=1)[0]
        assert name.lower().replace("_", "-") in pins
    assert "certifi>=2026.10.19" in project["dependencies"]
    assert tuple(map(int, pins["certifi"][None].split("."))) >= (2026, 10, 19)


def test_deploy_bootstraps_pip_before_dependency_download() -> None:
    deploy = (ROOT / "deploy/deploy.sh").read_text()
    bootstrap = (ROOT / "scripts/ensure-safe-pip.sh").read_text()
    assert deploy.index("bash scripts/ensure-safe-pip.sh") < deploy.index("pip install -r requirements.lock")
    assert deploy.index("pip install -r requirements.lock") < deploy.index("pip install -e . --no-deps")
    assert "--upgrade pip" not in deploy
    assert "pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70" in bootstrap
