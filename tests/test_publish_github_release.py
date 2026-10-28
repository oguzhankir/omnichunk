"""The release helper must publish only the requested release."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish_github_release.py"
spec = importlib.util.spec_from_file_location("publish_github_release", SCRIPT)
assert spec is not None and spec.loader is not None
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


@pytest.mark.parametrize("exists", [True, False])
def test_release_helper_only_creates_release_when_missing(tmp_path, monkeypatch, exists):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("RELEASE_TAG", "v2.3.0")
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "release-notes-2.3.0.md").write_text("Notes")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "package.whl").write_text("artifact")
    monkeypatch.setattr(
        publisher.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0 if exists else 1)
    )
    calls = []
    monkeypatch.setattr(publisher, "gh", lambda *args: calls.append(args))
    publisher.main()
    if exists:
        assert not calls
    else:
        assert len(calls) == 1
        assert calls[0][:3] == ("release", "create", "v2.3.0")
        assert "--verify-tag" in calls[0]
        assert "dist/package.whl" in calls[0]


def test_release_helper_requires_notes_before_publication(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("RELEASE_TAG", "v2.3.0")
    with pytest.raises(ValueError, match="release notes"):
        publisher.main()
