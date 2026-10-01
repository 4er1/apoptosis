"""Estado de salud: tabla de texto y dashboard HTML autocontenido (sin dependencias)."""
from __future__ import annotations

from html import escape

from .health import judge
from .store import State

ORDER = {"flaky": 0, "quarantined": 0, "suspect": 1, "broken": 2, "changed": 3, "learning": 4, "healthy": 5}
CHIP = {"quarantined": "#d1242f", "suspect": "#bf8700", "broken": "#e16f24", "changed": "#3b82c4",
        "learning": "#6e7781", "healthy": "#1a7f37", "flaky": "#d1242f"}


def rows(state: State, threshold=0.75, min_attempts=10, window=30) -> list[dict]:
    out = []
    for nid, r in state.tests.items():
        v = judge(r.outcomes(), threshold=threshold, min_attempts=min_attempts, window=window)
        status = "quarantined" if r.quarantined else v.status
        out.append({"nodeid": nid, "status": status, "health": v.health, "attempts": v.attempts, "fails": v.fails,
                    "flips": v.flips, "trail": r.outcomes()[-window:], "issue": r.issue, "kill": r.kill,
                    "heal_streak": r.heal_streak})
    return sorted(out, key=lambda x: (ORDER.get(x["status"], 9), x["health"], x["nodeid"]))


def text_table(rs: list[dict], heal_passes: int = 10) -> str:
    if not rs:
        return "(sin datos todavía: ejecuta pytest con --apoptosis)"
    w = min(70, max(len(r["nodeid"]) for r in rs))
    lines = [f"{'TEST':<{w}}  {'ESTADO':<11} {'SALUD':>5}  {'FALLOS':>7}  EXTRA"]
    for r in rs:
        extra = ""
        if r["status"] == "quarantined":
            extra = f"racha de curación {r['heal_streak']}/{heal_passes}" + (f" · issue #{r['issue']['number']}" if r["issue"] else "")
        nid = r["nodeid"] if len(r["nodeid"]) <= w else "…" + r["nodeid"][-(w - 1):]
        health = "  roto" if r["status"] == "broken" else f"{r['health']:>5.2f}"
        lines.append(f"{nid:<{w}}  {r['status']:<11} {health}  {r['fails']:>3}/{r['attempts']:<3}  {extra}")
    return "\n".join(lines)


def html(rs: list[dict], title="Apoptosis", heal_passes: int = 10) -> str:
    count = lambda s: sum(1 for r in rs if r["status"] == s)  # noqa: E731
    cards = "".join(f'<div class="card"><b>{n}</b><span>{label}</span></div>' for n, label in [
        (len(rs), "tests registrados"), (count("quarantined"), "en cuarentena"), (count("suspect"), "sospechosos"),
        (count("broken"), "rotos (bug real)"), (count("healthy"), "sanos")])
    body = []
    for r in rs:
        trail = "".join(f'<i class="{"p" if ok else "f"}" title="{"pasó" if ok else "falló"}"></i>' for ok in r["trail"])
        extra = ""
        if r["status"] == "quarantined":
            extra = f'curación {r["heal_streak"]}/{heal_passes}'
            if r["issue"]:
                extra += f' · <a href="{escape(r["issue"]["url"])}">issue #{r["issue"]["number"]}</a>' if r["issue"]["url"] else f' · issue #{r["issue"]["number"]}'
        body.append(
            f'<tr><td><code>{escape(r["nodeid"])}</code></td>'
            f'<td><span class="chip" style="background:{CHIP.get(r["status"], "#6e7781")}">{r["status"]}</span></td>'
            + (f'<td><div class="bar"><i class="bad" style="width:100%"></i></div>roto</td>' if r["status"] == "broken" else
               f'<td><div class="bar"><i style="width:{r["health"] * 100:.0f}%"></i></div>{r["health"]:.2f}</td>')
            + f'<td>{r["fails"]}/{r["attempts"]}</td><td class="trail">{trail}</td><td>{extra}</td></tr>')
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>
:root{{--bg:#0e1116;--card:#161b22;--fg:#e6edf3;--mut:#8b949e;--line:#2a313c;--ok:#2dd4bf}}
@media (prefers-color-scheme:light){{:root{{--bg:#f6f8fa;--card:#fff;--fg:#1f2328;--mut:#59636e;--line:#d0d7de;--ok:#0f9d8a}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1050px;margin:0 auto;padding:28px 18px 60px}}h1{{margin:0;font-size:26px}}.mut{{color:var(--mut);font-size:13px}}
.grid{{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));margin:18px 0}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}}.card b{{display:block;font-size:26px;line-height:1.1}}.card span{{color:var(--mut);font-size:13px}}
.wrap{{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}}table{{width:100%;border-collapse:collapse}}
th,td{{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);font-size:14px;vertical-align:middle}}th{{color:var(--mut);font-size:12px}}
code{{font:12.5px ui-monospace,Menlo,Consolas,monospace;word-break:break-all}}.chip{{color:#fff;border-radius:6px;padding:1px 8px;font-size:12px;font-weight:600}}
.bar{{display:inline-block;vertical-align:middle;width:70px;height:8px;border-radius:4px;background:var(--line);margin-right:8px;overflow:hidden}}.bar i{{display:block;height:100%;background:var(--ok)}}.bar i.bad{{background:#d1242f}}
.trail{{white-space:nowrap}}.trail i{{display:inline-block;width:7px;height:16px;border-radius:2px;margin-right:2px}}.trail .p{{background:#2da44e}}.trail .f{{background:#d1242f}}a{{color:var(--ok)}}
</style></head><body><main><h1>🦋 Apoptosis</h1>
<div class="mut">Salud = 1 − 2·min(%pasa, %falla). Un test que falla siempre está <em>roto</em>, no es flaky, y no se cuarentena.</div>
<div class="grid">{cards}</div><div class="wrap"><table><tr><th>Test</th><th>Estado</th><th>Salud</th><th>Fallos</th><th>Últimos intentos</th><th></th></tr>{''.join(body)}</table></div></main></body></html>"""
