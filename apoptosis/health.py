"""Índice de salud de un test. Funciones puras: fáciles de razonar y de testear.

Idea clave: un test que falla SIEMPRE no es flaky, está roto (bug real) y NO se cuarentena;
uno que pasaba y empezó a fallar de forma estable tampoco (regresión). Flaky = resultados inconsistentes
con vaivén: pasa y falla alternándose sin cambios en el código.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Verdict:
    status: str       # learning | healthy | broken | changed | suspect | flaky
    health: float     # 1.0 = totalmente estable · 0.0 = moneda al aire
    attempts: int
    fails: int
    flips: int        # cambios pass<->fail consecutivos
    flip_rate: float

    @property
    def kill(self) -> bool:
        return self.status == "flaky"


def judge(outcomes: list[bool], *, threshold: float = 0.75, min_attempts: int = 10, window: int = 30) -> Verdict:
    """outcomes: True = pasó, en orden cronológico. Solo se mira la ventana de los últimos `window` intentos.

    health = 1 - 2·min(p_pass, p_fail)      (0 con 50/50, 1 si todos iguales; no depende del orden)
      · 1 fallo en 10 → 0.80 · 2 en 10 → 0.60 · 3 en 10 → 0.40 · 5 en 10 → 0.00

    status:
      learning  menos de `min_attempts` intentos: no se juzga todavía
      healthy   nunca falló
      broken    siempre falla → bug real, el test hace su trabajo (NO se cuarentena)
      changed   un único cambio de estado (ej. PPPPFFFF) → regresión o arreglo, no flakiness
      suspect   vaivén (≥2 cambios) pero salud ≥ umbral
      flaky     vaivén (≥2 cambios) y salud < umbral → se mata
    """
    xs = outcomes[-window:]
    n = len(xs)
    passes = sum(xs)
    fails = n - passes
    flips = sum(1 for a, b in zip(xs, xs[1:]) if a != b)
    flip_rate = flips / (n - 1) if n > 1 else 0.0
    health = round(1.0 - (2 * min(passes, fails) / n if n else 0.0), 4)
    if n < min_attempts:
        status = "learning"
    elif fails == 0:
        status = "healthy"
    elif passes == 0:
        status = "broken"
    elif flips <= 1:
        status = "changed"
    elif health < threshold:
        status = "flaky"
    else:
        status = "suspect"
    return Verdict(status, health, n, fails, flips, round(flip_rate, 4))
