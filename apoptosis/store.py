"""Registro de eventos (event sourcing) en JSON Lines + estado derivado.

Un solo archivo append-only (`.apoptosis/events.jsonl`): cada proceso solo AÑADE líneas (O_APPEND), así que es
seguro con varios procesos (pytest-xdist) y se puede versionar/cachear en CI. El estado (qué está en
cuarentena, rachas de curación, issues) se calcula reproduciendo los eventos.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

EVENTS_FILE = "events.jsonl"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class Record:
    nodeid: str
    attempts: list = field(default_factory=list)  # intentos normales/scan desde el último reinicio
    quarantined: bool = False
    kill: dict | None = None
    heal_streak: int = 0                           # pasadas consecutivas en modo curación
    heal_attempts: int = 0
    issue: dict | None = None                      # {"number", "url", "open"}
    released: dict | None = None

    def outcomes(self) -> list[bool]:
        return [a["outcome"] == "pass" for a in self.attempts]


class State:
    def __init__(self):
        self.tests: dict[str, Record] = {}

    def rec(self, nodeid: str) -> Record:
        return self.tests.setdefault(nodeid, Record(nodeid))

    @classmethod
    def from_events(cls, events) -> "State":
        s = cls()
        for e in events:
            s.apply(e)
        return s

    def apply(self, e: dict) -> None:
        t, nid = e.get("type"), e.get("nodeid")
        if not nid:
            return
        r = self.rec(nid)
        if t == "attempt":
            if e.get("mode") == "heal":
                r.heal_attempts += 1
                r.heal_streak = r.heal_streak + 1 if e["outcome"] == "pass" else 0
            else:
                r.attempts.append(e)
        elif t == "kill":
            r.quarantined, r.kill, r.heal_streak, r.heal_attempts = True, e, 0, 0
        elif t == "release":
            r.quarantined, r.kill, r.released = False, None, e
            r.attempts, r.heal_streak, r.heal_attempts = [], 0, 0
        elif t == "reset":
            r.attempts = []
        elif t == "issue":
            was_open = bool(r.issue and r.issue["open"])
            opened = {"created": True, "reopened": True, "closed": False}.get(e.get("action"), was_open)
            r.issue = {"number": e["number"], "url": e.get("url", ""), "open": opened}


class Store:
    def __init__(self, directory):
        self.dir = Path(directory)
        self.path = self.dir / EVENTS_FILE

    def append(self, *events: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        data = "".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n" for e in events)
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, data.encode("utf-8"))
        finally:
            os.close(fd)

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue  # línea corrupta (p. ej. proceso cortado a mitad): se ignora
        return out

    def state(self) -> State:
        return State.from_events(self.load())

    def compact(self, keep: int = 30) -> tuple[int, int]:
        """Reescribe el log con el mínimo que reproduce el mismo estado. Devuelve (eventos antes, después)."""
        events = self.load()
        state = State.from_events(events)
        out: list[dict] = []
        for nid, r in state.tests.items():
            out.extend(r.attempts[-keep:])
            if r.kill:
                out.append(r.kill)
                out.extend({"type": "attempt", "nodeid": nid, "outcome": "pass", "mode": "heal", "ts": now()}
                           for _ in range(r.heal_streak))
            if r.issue:
                out.append({"type": "issue", "nodeid": nid, "number": r.issue["number"], "url": r.issue["url"],
                            "action": "created" if r.issue["open"] else "closed", "ts": now()})
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n" for e in out),
                       encoding="utf-8")
        os.replace(tmp, self.path)
        return len(events), len(out)
