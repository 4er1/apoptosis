import pytest

from apoptosis.health import judge


def v(s, **kw):
    return judge([c == "P" for c in s], **kw)


@pytest.mark.parametrize("trail,status", [
    ("PPPPPPPPPP", "healthy"),
    ("FFFFFFFFFF", "broken"),          # siempre falla: bug real, no flaky
    ("PPPPPPFFFF", "changed"),         # una regresión estable no es flakiness
    ("FFFFPPPPPP", "changed"),         # un arreglo estable tampoco
    ("PPPPFPPPPP", "suspect"),         # 1 fallo en 10: vaivén pero salud 0.80 >= 0.75
    ("PFPPFPPFPP", "flaky"),
    ("PFPFPFPFPF", "flaky"),
    ("PPFPP", "learning"),             # pocos datos: no se juzga
])
def test_status(trail, status):
    assert v(trail).status == status


def test_la_salud_no_depende_del_orden():
    assert v("PPPPPPPPFF").health == v("PFPPPFPPPP").health == 0.6


@pytest.mark.parametrize("fails,health", [(0, 1.0), (1, 0.8), (2, 0.6), (3, 0.4), (5, 0.0), (10, 1.0)])
def test_salud_segun_fallos_en_10(fails, health):
    assert v("F" * fails + "P" * (10 - fails)).health == health


def test_solo_cuenta_la_ventana_reciente():
    old_flaky = "PFPFPFPFPF" * 2
    assert v(old_flaky + "P" * 30, window=30).status == "healthy"


def test_umbral_y_min_attempts_configurables():
    assert v("PFPPFPPFPP", threshold=0.3).status == "suspect"
    assert v("PFPPFPPFPP", min_attempts=20).status == "learning"


def test_kill_solo_si_flaky():
    assert v("PFPFPFPFPF").kill and not v("FFFFFFFFFF").kill and not v("PPPPPPPPPP").kill
