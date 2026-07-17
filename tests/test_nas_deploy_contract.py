from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_nas_git_dockerfile_is_self_contained() -> None:
    """The NAS image must build directly from a clean Git checkout."""
    dockerfile = (ROOT / "Dockerfile.git.nas").read_text(encoding="utf-8")

    assert "COPY . /app" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "_nas_runtime_patch.py" not in dockerfile


def test_nas_deploy_script_builds_from_git_and_runs_tests() -> None:
    """Keep NAS deployments command-driven, reproducible and validated."""
    script = (ROOT / "nas_deploy_from_git.sh").read_text(encoding="utf-8")

    assert "git clone" in script
    assert "git reset --hard" in script
    assert "Dockerfile.git.nas" in script
    assert "python -m pytest -q" in script
    assert "python -m compileall -q" in script
    assert "fridgechef_predeploy_" in script
    assert "_stcore/health" in script
