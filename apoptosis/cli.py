from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import report
from .store import Store, now


def find_dir(start=None) -> str:
    """Sin -d: busca .apoptosis en el cwd y hacia arriba (como git); el plugin lo guarda en la raíz de pytest."""
    here = Path(start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / ".apoptosis").is_dir():
            return str(d / ".apoptosis")
    return str(here / ".apoptosis")


def _common(p):
    p.add_argument("-d", "--dir", default=None, help="carpeta del estado (default: .apoptosis más cercano hacia arriba)")
    p.add_argument("--threshold", type=float, default=0.75)
    p.add_argument("--min-attempts", type=int, default=10)
    p.add_argument("--window", type=int, default=30)


def main(argv=None) -> int:
    try:  # `apoptosis status | head` no debe imprimir un traceback
        import signal
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(prog="apoptosis", description="Estado de salud de tus tests (plugin pytest-apoptosis)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status", help="tabla de salud por test")
    _common(s)
    r = sub.add_parser("report", help="dashboard HTML")
    _common(r)
    r.add_argument("-o", "--output", default="apoptosis-report.html")
    q = sub.add_parser("release", help="reintegra a mano un test en cuarentena")
    _common(q)
    q.add_argument("nodeid")
    c = sub.add_parser("compact", help="reduce el log de eventos conservando el estado")
    _common(c)
    c.add_argument("--keep", type=int, default=30)
    a = ap.parse_args(argv)

    store = Store(a.dir or find_dir())
    if a.cmd in ("status", "report"):
        rs = report.rows(store.state(), a.threshold, a.min_attempts, a.window)
        if a.cmd == "status":
            print(report.text_table(rs))
        else:
            with open(a.output, "w", encoding="utf-8") as f:
                f.write(report.html(rs))
            print(a.output)
    elif a.cmd == "release":
        r_ = store.state().tests.get(a.nodeid)
        if not r_ or not r_.quarantined:
            print(f"✗ {a.nodeid} no está en cuarentena", file=sys.stderr)
            return 1
        store.append({"type": "release", "ts": now(), "session": "cli", "nodeid": a.nodeid, "reason": "manual", "streak": 0})
        print(f"✅ {a.nodeid} reintegrado (su historial se reinicia)")
    elif a.cmd == "compact":
        before, after = store.compact(a.keep)
        print(f"eventos: {before} → {after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
