# 🦋 Test flaky en cuarentena: test_demo.py::test_flaky_moneda_30pct

## 🦋 Apoptosis puso este test en cuarentena

**`test_demo.py::test_flaky_moneda_30pct`** dejó de ejecutarse en el pipeline (se marca como *skipped*) hasta que alguien lo repare.

| Salud | Umbral | Intentos | Fallos | Cambios pass↔fail |
|---|---|---|---|---|
| **0.17** | 0.75 | 12 | 5 | 5 |

> Salud = 1 − 2·min(%pasa, %falla). Un test que falla *siempre* no es flaky (está roto) y no se cuarentena.

### Historial (últimos 12 intentos)

| # | Fecha (UTC) | Resultado | Seed | Duración | Mensaje |
|---|---|---|---|---|---|
| 1 | 2026-10-01T23:30:34Z | ❌ falló | 100 | 0.00s | AssertionError: timeout simulado esperando al servicio assert 0.1456692551041303 > 0.3 + … |
| 2 | 2026-10-01T23:30:34Z | ✅ pasó | 101 | 0.00s |  |
| 3 | 2026-10-01T23:30:34Z | ❌ falló | 102 | 0.00s | AssertionError: timeout simulado esperando al servicio assert 0.1481712063870836 > 0.3 + … |
| 4 | 2026-10-01T23:30:34Z | ✅ pasó | 103 | 0.00s |  |
| 5 | 2026-10-01T23:30:34Z | ✅ pasó | 104 | 0.00s |  |
| 6 | 2026-10-01T23:30:34Z | ✅ pasó | 105 | 0.00s |  |
| 7 | 2026-10-01T23:30:34Z | ✅ pasó | 106 | 0.00s |  |
| 8 | 2026-10-01T23:30:34Z | ❌ falló | 107 | 0.00s | AssertionError: timeout simulado esperando al servicio assert 0.24648195966935815 > 0.3 +… |
| 9 | 2026-10-01T23:30:34Z | ❌ falló | 108 | 0.00s | AssertionError: timeout simulado esperando al servicio assert 0.13052022990067025 > 0.3 +… |
| 10 | 2026-10-01T23:30:34Z | ❌ falló | 109 | 0.00s | AssertionError: timeout simulado esperando al servicio assert 0.27958303860586786 > 0.3 +… |
| 11 | 2026-10-01T23:30:34Z | ✅ pasó | 110 | 0.00s |  |
| 12 | 2026-10-01T23:30:34Z | ✅ pasó | 111 | 0.00s |  |

### Mensajes de fallo distintos
- (5×) `AssertionError: timeout simulado esperando al servicio assert 0.1456692551041303 > 0.3 + where 0.1456692551041303 = <built-in method random of Random object at 0x31157ea0>() + where <built-in method …`

### Cómo reproducirlo
```bash
pytest "test_demo.py::test_flaky_moneda_30pct" --apoptosis --apoptosis-runs 20 --apoptosis-seed 100
```
Las semillas con las que falló quedan en la tabla: `random` y `numpy` se siembran con ellas y el fixture `apoptosis_seed` las expone.

### Cómo se reintegra
Cuando lo arregles: `pytest --apoptosis-heal` ejecuta solo los tests en cuarentena y lo reintegra tras **10 pasadas consecutivas**
(un fallo reinicia la racha). Este issue se cierra solo al reintegrarlo.
