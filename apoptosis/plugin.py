"""Plugin de Pytest: ejecuta cada test N veces con semillas distintas, mide su salud, cuarentena los flaky,
abre issues en GitHub y reintegra los que se curan. Es OPT-IN: no hace nada sin --apoptosis (o sus derivados)."""
from __future__ import annotations

import json
import os
import secrets
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from _pytest.reports import TestReport
from _pytest.runner import runtestprotocol

from . import issues as iss
from .github import GitHubError, from_env
from .health import judge
from .store import Store, now

RUNTIME = "apoptosis-runtime"


# ---------------------------------------------------------------- opciones
def pytest_addoption(parser):
    g = parser.getgroup("apoptosis", "Apoptosis: cuarentena automática de tests flaky")
    g.addoption("--apoptosis", action="store_true", default=False, help="activa el plugin (registra resultados y salta los tests en cuarentena)")
    g.addoption("--apoptosis-runs", type=int, default=None, help="ejecuta cada test N veces con semillas distintas (default 1)")
    g.addoption("--apoptosis-heal", action="store_true", default=False, help="modo curación: ejecuta solo los tests en cuarentena y reintegra los que pasan K veces seguidas")
    g.addoption("--apoptosis-heal-passes", type=int, default=None, help="pasadas consecutivas para reintegrar (default 10)")
    g.addoption("--apoptosis-threshold", type=float, default=None, help="salud mínima antes de matar un test flaky (default 0.75)")
    g.addoption("--apoptosis-min-attempts", type=int, default=None, help="intentos mínimos antes de juzgar un test (default 10)")
    g.addoption("--apoptosis-window", type=int, default=None, help="cuántos intentos recientes se miran (default 30)")
    g.addoption("--apoptosis-dir", default=None, help="carpeta del estado (default .apoptosis en la raíz del proyecto)")
    g.addoption("--apoptosis-seed", type=int, default=None, help="semilla base (default aleatoria; sirve para reproducir un fallo)")
    g.addoption("--apoptosis-github-repo", default=None, help="owner/repo donde abrir issues (default $GITHUB_REPOSITORY)")
    g.addoption("--apoptosis-no-issues", action="store_true", default=False, help="no abrir issues en GitHub (solo archivos locales)")
    parser.addini("apoptosis", "activa Apoptosis", type="bool", default=False)
    for name in ("runs", "heal_passes", "threshold", "min_attempts", "window", "dir", "seed", "github_repo"):
        parser.addini(f"apoptosis_{name}", f"equivalente a --apoptosis-{name.replace('_', '-')}", default="")


@dataclass
class Settings:
    enabled: bool
    runs: int
    heal: bool
    heal_passes: int
    threshold: float
    min_attempts: int
    window: int
    directory: Path
    seed: int
    repo: str | None
    issues: bool


def _opt(config, name, default, cast=str):
    v = config.getoption(f"apoptosis_{name}", default=None)
    if v is not None:
        return v
    raw = config.getini(f"apoptosis_{name}")
    return cast(raw) if raw not in ("", None) else default


def _settings(config) -> Settings:
    runs = _opt(config, "runs", None, int)
    heal = bool(config.getoption("apoptosis_heal"))
    enabled = bool(config.getoption("apoptosis") or config.getini("apoptosis") or runs or heal)
    directory = Path(_opt(config, "dir", ".apoptosis"))
    if not directory.is_absolute():
        directory = config.rootpath / directory
    wi = getattr(config, "workerinput", {})
    return Settings(
        enabled=enabled, runs=max(1, runs or 1), heal=heal, heal_passes=_opt(config, "heal_passes", 10, int),
        threshold=_opt(config, "threshold", 0.75, float), min_attempts=_opt(config, "min_attempts", 10, int),
        window=_opt(config, "window", 30, int), directory=directory,
        seed=wi.get("apoptosis_seed", _opt(config, "seed", secrets.randbelow(2**31), int)),
        repo=_opt(config, "github_repo", None), issues=not config.getoption("apoptosis_no_issues"))


def pytest_configure(config):
    config.addinivalue_line("markers", "apoptosis_immune: nunca cuarentenar este test (se sigue midiendo y avisando)")
    s = _settings(config)
    if s.enabled:
        config.pluginmanager.register(Apoptosis(config, s), RUNTIME)


@pytest.fixture
def apoptosis_seed(request):
    """Semilla del intento en curso (random/numpy ya vienen sembrados con ella)."""
    p = request.config.pluginmanager.get_plugin(RUNTIME)
    return p.current_seed if p else int(os.environ.get("APOPTOSIS_SEED", "0"))


# ---------------------------------------------------------------- utilidades
def _outcome(reports) -> str:
    if any(r.failed for r in reports):
        return "fail"
    if any(r.skipped for r in reports):
        return "skip"  # skip / xfail: no hay nada que medir
    return "pass"


def _message(reports) -> str:
    for r in reports:
        if r.failed:
            crash = getattr(r.longrepr, "reprcrash", None)
            msg = getattr(crash, "message", None) or (str(r.longrepr).strip().splitlines() or [""])[-1]
            return msg[:300]
    return ""


def _skip_report(item, reason: str) -> TestReport:
    lineno = (item.location[1] or 0) + 1
    return TestReport(nodeid=item.nodeid, location=item.location, keywords={k: 1 for k in item.keywords},
                      outcome="skipped", longrepr=(str(item.path), lineno, f"Skipped: {reason}"), when="call",
                      sections=[], duration=0.0, user_properties=item.user_properties)


def _is_quarantine_skip(item) -> bool:
    m = item.get_closest_marker("skip")
    return bool(m and str(m.kwargs.get("reason", "")).startswith("apoptosis:"))


# ---------------------------------------------------------------- plugin
class Apoptosis:
    def __init__(self, config, settings: Settings):
        self.config, self.cfg = config, settings
        self.is_worker = hasattr(config, "workerinput")
        self.session_id = getattr(config, "workerinput", {}).get("apoptosis_session") or uuid.uuid4().hex[:8]
        self.store = Store(settings.directory)
        self.state = self.store.state()
        self.current_seed = settings.seed
        self.notes: list[str] = []

    # -- cabecera / xdist ------------------------------------------------
    def pytest_report_header(self):
        n = sum(1 for r in self.state.tests.values() if r.quarantined)
        mode = f"curación (K={self.cfg.heal_passes})" if self.cfg.heal else f"runs={self.cfg.runs}"
        return [f"apoptosis: {mode} · umbral {self.cfg.threshold} · {n} en cuarentena · seed base {self.cfg.seed}"]

    @pytest.hookimpl(optionalhook=True)
    def pytest_configure_node(self, node):
        node.workerinput["apoptosis_session"] = self.session_id
        node.workerinput["apoptosis_seed"] = self.cfg.seed

    # -- colección: cuarentena -------------------------------------------
    def pytest_collection_modifyitems(self, config, items):
        quarantined = {nid: r for nid, r in self.state.tests.items() if r.quarantined}
        if self.cfg.heal:
            keep = [i for i in items if i.nodeid in quarantined]
            drop = [i for i in items if i.nodeid not in quarantined]
            if drop:
                config.hook.pytest_deselected(items=drop)
            items[:] = keep
            return
        for item in items:
            r = quarantined.get(item.nodeid)
            if r:
                issue = f" · issue #{r.issue['number']}" if r.issue else ""
                since = (r.kill or {}).get("ts", "?")
                item.add_marker(pytest.mark.skip(
                    reason=f"apoptosis: en cuarentena desde {since} (salud {(r.kill or {}).get('health', 0):.2f}){issue}"))

    # -- ejecución --------------------------------------------------------
    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_protocol(self, item, nextitem):
        item.ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
        if _is_quarantine_skip(item):
            self._emit(item, runtestprotocol(item, nextitem=nextitem, log=False))
        elif self.cfg.heal:
            self._heal(item, nextitem)
        else:
            self._scan(item, nextitem)
        item.ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)
        return True

    def _seed(self, seed: int) -> None:
        import random

        self.current_seed = seed
        os.environ["APOPTOSIS_SEED"] = str(seed)
        random.seed(seed)
        np = sys.modules.get("numpy")
        if np is not None:
            np.random.seed(seed % 2**32)

    def _attempt(self, item, nextitem, seed: int):
        self._seed(seed)
        reports = runtestprotocol(item, nextitem=nextitem, log=False)
        outcome = _outcome(reports)
        return reports, outcome, sum(r.duration for r in reports), (_message(reports) if outcome == "fail" else "")

    def _event(self, item, outcome, seed, duration, message, mode) -> dict:
        e = {"type": "attempt", "ts": now(), "session": self.session_id, "nodeid": item.nodeid, "outcome": outcome,
             "seed": seed, "duration": round(duration, 4), "mode": mode}
        if message:
            e["message"] = message
        return e

    def _record(self, *events) -> None:
        self.store.append(*events)
        for e in events:
            self.state.apply(e)

    @staticmethod
    def _emit(item, reports) -> None:
        for r in reports:
            item.ihook.pytest_runtest_logreport(report=r)

    def _scan(self, item, nextitem) -> None:
        attempts = []
        for i in range(self.cfg.runs):
            a = self._attempt(item, nextitem, self.cfg.seed + i)
            attempts.append((a, self.cfg.seed + i))
            if a[1] == "skip":
                break
        measured = [(a, s) for a, s in attempts if a[1] in ("pass", "fail")]
        self._record(*(self._event(item, o, s, d, m, "scan") for (_, o, d, m), s in measured))
        rec = self.state.rec(item.nodeid)
        verdict = judge(rec.outcomes(), threshold=self.cfg.threshold, min_attempts=self.cfg.min_attempts,
                        window=self.cfg.window)
        failed = [a for a, _ in measured if a[1] == "fail"]
        immune = item.get_closest_marker("apoptosis_immune") is not None
        if measured and verdict.kill and not immune and not rec.quarantined:
            self._record({"type": "kill", "ts": now(), "session": self.session_id, "nodeid": item.nodeid,
                          "health": verdict.health, "flip_rate": verdict.flip_rate, "attempts": verdict.attempts,
                          "fails": verdict.fails, "reason": "salud bajo el umbral"})
            self._emit(item, [_skip_report(item, f"apoptosis: test flaky cuarentenado (salud {verdict.health:.2f} < "
                                                 f"{self.cfg.threshold}, {verdict.fails}/{verdict.attempts} fallos)")])
        elif failed:
            reports = failed[0][0]
            note = (f"falló {len(failed)} de {len(measured)} intentos en esta ejecución (salud {verdict.health:.2f}, "
                    f"estado: {verdict.status})")
            next(r for r in reports if r.failed).sections.append(("apoptosis", note))
            self._emit(item, reports)
        else:
            self._emit(item, attempts[-1][0][0])

    def _heal(self, item, nextitem) -> None:
        rec = self.state.rec(item.nodeid)
        last_reports, failed = None, False
        while rec.heal_streak < self.cfg.heal_passes:
            seed = self.cfg.seed + rec.heal_attempts
            reports, outcome, dur, msg = self._attempt(item, nextitem, seed)
            if outcome == "skip":
                last_reports = reports
                break
            self._record(self._event(item, outcome, seed, dur, msg, "heal"))
            last_reports = reports
            if outcome == "fail":
                failed = True
                break
        if rec.heal_streak >= self.cfg.heal_passes:
            self._record({"type": "release", "ts": now(), "session": self.session_id, "nodeid": item.nodeid,
                          "reason": "healed", "streak": rec.heal_streak})
            self._emit(item, last_reports)
        elif failed:
            self._emit(item, [_skip_report(item, f"apoptosis heal: sigue inestable, racha reiniciada "
                                                  f"(se necesitan {self.cfg.heal_passes} pasadas seguidas)")])
        else:
            self._emit(item, last_reports)

    # -- cierre: issues, snapshot, resumen --------------------------------
    def pytest_sessionfinish(self, session, exitstatus):
        if self.is_worker:
            return
        state = self.store.state()
        self._snapshot(state)
        self._sync_issues(state)
        if self.cfg.heal and exitstatus == pytest.ExitCode.NO_TESTS_COLLECTED:
            session.exitstatus = pytest.ExitCode.OK  # nada en cuarentena = nada que curar, no es un error

    def _snapshot(self, state) -> None:
        q = {nid: {"killed_at": r.kill.get("ts"), "health": r.kill.get("health"), "issue": (r.issue or {}).get("url"),
                   "heal_streak": r.heal_streak} for nid, r in state.tests.items() if r.quarantined}
        self.cfg.directory.mkdir(parents=True, exist_ok=True)
        (self.cfg.directory / "quarantine.json").write_text(
            json.dumps({"generated": now(), "note": "generado por Apoptosis; no editar (usa `apoptosis release`)",
                        "tests": q}, indent=1, ensure_ascii=False), encoding="utf-8")

    def _verdict(self, r):
        return judge(r.outcomes(), threshold=self.cfg.threshold, min_attempts=self.cfg.min_attempts, window=self.cfg.window)

    def _sync_issues(self, state) -> None:
        gh = from_env(self.cfg.repo) if self.cfg.issues else None
        for nid, r in state.tests.items():
            if r.quarantined and r.kill and not (r.issue and r.issue["open"]):
                body = iss.render_kill(nid, r.attempts, self._verdict(r), threshold=self.cfg.threshold,
                                       heal_passes=self.cfg.heal_passes)
                if r.kill.get("session") == self.session_id:
                    d = self.cfg.directory / "issues"
                    d.mkdir(parents=True, exist_ok=True)
                    (d / f"{iss.slug(nid)}.md").write_text(f"# {iss.title(nid)}\n\n{body}", encoding="utf-8")
                if not gh:
                    continue
                try:
                    if r.issue:
                        gh.set_state(r.issue["number"], "open")
                        gh.comment(r.issue["number"], iss.render_rekill(nid, body))
                        ev = {"number": r.issue["number"], "url": r.issue["url"], "action": "reopened"}
                    else:
                        res = gh.create_issue(iss.title(nid), body, iss.LABELS)
                        ev = {"number": res["number"], "url": res.get("html_url", ""), "action": "created"}
                    self.store.append({"type": "issue", "ts": now(), "nodeid": nid, **ev})
                    self.notes.append(f"issue #{ev['number']} {ev['action']}: {nid}")
                except (GitHubError, KeyError) as e:
                    self.notes.append(f"⚠ no pude sincronizar el issue de {nid}: {e}")
            elif gh and not r.quarantined and r.issue and r.issue["open"]:
                try:
                    gh.comment(r.issue["number"], iss.render_heal(nid, (r.released or {}).get("streak", self.cfg.heal_passes)))
                    gh.set_state(r.issue["number"], "closed")
                    self.store.append({"type": "issue", "ts": now(), "nodeid": nid, "number": r.issue["number"],
                                       "url": r.issue["url"], "action": "closed"})
                    self.notes.append(f"issue #{r.issue['number']} cerrado: {nid}")
                except GitHubError as e:
                    self.notes.append(f"⚠ no pude cerrar el issue de {nid}: {e}")

    def pytest_terminal_summary(self, terminalreporter):
        tr = terminalreporter
        mine = [e for e in self.store.load() if e.get("session") == self.session_id]
        state = self.store.state()
        kills = [e for e in mine if e["type"] == "kill"]
        released = [e for e in mine if e["type"] == "release"]
        touched = {e["nodeid"] for e in mine if e["type"] == "attempt" and e.get("mode") != "heal"}
        suspects = [(nid, self._verdict(state.tests[nid])) for nid in sorted(touched)]
        suspects = [(n, v) for n, v in suspects if v.status == "suspect"]
        total_q = sum(1 for r in state.tests.values() if r.quarantined)
        if not (kills or released or suspects or self.notes or total_q):
            return
        tr.write_sep("=", "apoptosis")
        for e in kills:
            tr.write_line(f"🦋 cuarentena: {e['nodeid']}  (salud {e['health']:.2f}, {e['fails']}/{e['attempts']} fallos)", yellow=True)
        for e in released:
            tr.write_line(f"✅ reintegrado: {e['nodeid']}  ({e.get('streak')} pasadas seguidas)", green=True)
        for nid, v in suspects:
            tr.write_line(f"👀 sospechoso: {nid}  (salud {v.health:.2f}, {v.fails}/{v.attempts} fallos)")
        for n in self.notes:
            tr.write_line(n)
        tr.write_line(f"{total_q} test(s) en cuarentena · estado en {self.cfg.directory}")
