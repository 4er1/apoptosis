import pytest

from apoptosis import issues
from apoptosis.github import GitHub, GitHubError, from_env
from apoptosis.health import judge


def test_crear_comentar_y_cerrar(fake_github):
    gh = from_env()
    res = gh.create_issue("título", "cuerpo", ["flaky-test"])
    gh.comment(res["number"], "hola")
    gh.set_state(res["number"], "closed")
    create, comment, patch = fake_github.requests
    assert res["number"] == 1 and res["html_url"].endswith("/issues/1")
    assert create["path"] == "/repos/me/repo/issues" and create["auth"] == "Bearer tok_test"
    assert create["body"] == {"title": "título", "body": "cuerpo", "labels": ["flaky-test"]}
    assert comment["path"].endswith("/issues/1/comments") and patch["body"] == {"state": "closed"}


def test_error_http_se_convierte_en_githuberror(fake_github):
    fake_github.fail_with = 500
    with pytest.raises(GitHubError, match="HTTP 500"):
        from_env().create_issue("t", "b", [])


def test_servidor_caido_se_convierte_en_githuberror():
    with pytest.raises(GitHubError):
        GitHub("o/r", "t", api="http://127.0.0.1:9", timeout=1).create_issue("t", "b", [])


def test_from_env_none_sin_token_o_repo(monkeypatch):
    for k in ("GITHUB_TOKEN", "APOPTOSIS_GITHUB_TOKEN", "GITHUB_REPOSITORY"):
        monkeypatch.delenv(k, raising=False)
    assert from_env() is None and from_env("o/r") is None


def test_cuerpo_del_issue():
    attempts = [{"outcome": "pass", "seed": 1, "duration": 0.1, "ts": "t1"},
                {"outcome": "fail", "seed": 7, "duration": 0.2, "ts": "t2", "message": "timeout 31s | `x`"},
                {"outcome": "fail", "seed": 9, "duration": 0.2, "ts": "t3", "message": "timeout 47s | `x`"}]
    body = issues.render_kill("t.py::test_a", attempts, judge([True, False, False]), threshold=0.75, heal_passes=10)
    assert 'pytest "t.py::test_a" --apoptosis --apoptosis-runs 20 --apoptosis-seed 7' in body
    assert "(2×)" in body                      # mismo mensaje con números distintos → un solo grupo
    assert "\\|" in body and "10 pasadas consecutivas" in body and "❌ falló" in body
