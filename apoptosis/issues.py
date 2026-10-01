"""Texto de los issues: historial de fallos, cómo reproducir, cómo se reintegra."""
from __future__ import annotations

import re

from .health import Verdict

LABELS = ["flaky-test", "apoptosis"]


def slug(nodeid: str) -> str:
    return re.sub(r"\W+", "_", nodeid).strip("_").lower()[:80] or "test"


def title(nodeid: str) -> str:
    return f"🦋 Test flaky en cuarentena: {nodeid}"


def _cell(text: str, n: int = 90) -> str:
    text = " ".join(str(text).split()).replace("|", "\\|").replace("`", "'")
    return text[: n - 1] + "…" if len(text) > n else text


def render_kill(nodeid: str, attempts: list[dict], v: Verdict, *, threshold: float, heal_passes: int,
                runs: int = 20) -> str:
    last = attempts[-runs:]
    rows = "\n".join(
        f"| {i} | {a.get('ts', '')} | {'✅ pasó' if a['outcome'] == 'pass' else '❌ falló'} | "
        f"{a.get('seed', '')} | {a.get('duration', 0):.2f}s | {_cell(a.get('message', ''))} |"
        for i, a in enumerate(last, 1))
    groups: dict[str, list] = {}  # agrupa por mensaje "normalizado" (los números cambian en cada intento)
    for a in attempts:
        if a["outcome"] == "fail" and a.get("message"):
            groups.setdefault(re.sub(r"\d+(?:\.\d+)?", "N", a["message"]), []).append(_cell(a["message"], 200))
    top = sorted(groups.values(), key=len, reverse=True)[:5]
    msg_list = "\n".join(f"- ({len(g)}×) `{g[0]}`" for g in top) or "- (sin mensaje)"
    fail_seeds = [a["seed"] for a in attempts if a["outcome"] == "fail" and "seed" in a][:3]
    seed_hint = f" --apoptosis-seed {fail_seeds[0]}" if fail_seeds else ""
    return f"""## 🦋 Apoptosis puso este test en cuarentena

**`{nodeid}`** dejó de ejecutarse en el pipeline (se marca como *skipped*) hasta que alguien lo repare.

| Salud | Umbral | Intentos | Fallos | Cambios pass↔fail |
|---|---|---|---|---|
| **{v.health:.2f}** | {threshold:.2f} | {v.attempts} | {v.fails} | {v.flips} |

> Salud = 1 − 2·min(%pasa, %falla). Un test que falla *siempre* no es flaky (está roto) y no se cuarentena.

### Historial (últimos {len(last)} intentos)

| # | Fecha (UTC) | Resultado | Seed | Duración | Mensaje |
|---|---|---|---|---|---|
{rows}

### Mensajes de fallo distintos
{msg_list}

### Cómo reproducirlo
```bash
pytest "{nodeid}" --apoptosis --apoptosis-runs 20{seed_hint}
```
Las semillas con las que falló quedan en la tabla: `random` y `numpy` se siembran con ellas y el fixture `apoptosis_seed` las expone.

### Cómo se reintegra
Cuando lo arregles: `pytest --apoptosis-heal` ejecuta solo los tests en cuarentena y lo reintegra tras **{heal_passes} pasadas consecutivas**
(un fallo reinicia la racha). Este issue se cierra solo al reintegrarlo.
"""


def render_heal(nodeid: str, streak: int) -> str:
    return (f"## ✅ Reintegrado\n\n`{nodeid}` pasó **{streak} veces consecutivas** en modo curación y vuelve al pipeline. "
            "Si vuelve a ser inestable, Apoptosis lo cuarentenará de nuevo y reabrirá este issue.")


def render_rekill(nodeid: str, body: str) -> str:
    return f"## ♻️ Volvió a la cuarentena\n\n`{nodeid}` se mostró inestable otra vez.\n\n{body}"
