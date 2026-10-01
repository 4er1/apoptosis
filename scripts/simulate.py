"""¿A partir de qué tasa de fallo Apoptosis mata a un test flaky? Monte Carlo sobre la función de salud real.

    python scripts/simulate.py            # 2000 pruebas por celda
Modela un test que falla con probabilidad p en cada intento, de forma independiente.
"""
import argparse
import random
import sys

sys.path.insert(0, __file__.rsplit("/", 2)[0])
from apoptosis.health import judge  # noqa: E402


def kill_rate(p, attempts, threshold, trials, rng, window=30):
    kills = 0
    for _ in range(trials):
        outs = [rng.random() >= p for _ in range(attempts)]
        kills += judge(outs, threshold=threshold, min_attempts=10, window=window).kill
    return kills / trials


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=2000)
    a = ap.parse_args()
    rng = random.Random(7)
    ps = [0.0, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50, 1.0]
    cfgs = [("10 intentos (1 scan)", 10, 0.75), ("30 intentos (3 scans)", 30, 0.75),
            ("30 intentos, umbral 0.90", 30, 0.90)]
    print("| tasa real de fallo | " + " | ".join(c[0] for c in cfgs) + " |\n|---|" + "---|" * len(cfgs))
    for p in ps:
        print(f"| {p:.0%} | " + " | ".join(f"{kill_rate(p, n, th, a.trials, rng):.0%}" for _, n, th in cfgs) + " |")


if __name__ == "__main__":
    main()
