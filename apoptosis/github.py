"""Cliente mínimo de la API REST de GitHub Issues (solo stdlib: urllib)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API = "https://api.github.com"


class GitHubError(RuntimeError):
    pass


class GitHub:
    def __init__(self, repo: str, token: str, api: str | None = None, timeout: float = 15):
        self.repo, self.token, self.timeout = repo, token, timeout
        self.api = (api or os.environ.get("APOPTOSIS_GITHUB_API") or API).rstrip("/")

    def _req(self, method: str, path: str, payload: dict | None = None) -> dict:
        req = urllib.request.Request(
            f"{self.api}/repos/{self.repo}{path}", method=method,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "apoptosis-pytest",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise GitHubError(f"{method} {path} → HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise GitHubError(f"{method} {path} → {e}") from e

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict:
        return self._req("POST", "/issues", {"title": title[:250], "body": body[:60000], "labels": labels})

    def comment(self, number: int, body: str) -> dict:
        return self._req("POST", f"/issues/{number}/comments", {"body": body[:60000]})

    def set_state(self, number: int, state: str) -> dict:
        assert state in ("open", "closed")
        return self._req("PATCH", f"/issues/{number}", {"state": state})


def from_env(repo: str | None = None) -> GitHub | None:
    """None si falta repositorio o token (entonces solo se escribe el issue en local)."""
    repo = repo or os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("APOPTOSIS_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    return GitHub(repo, token) if repo and token else None
