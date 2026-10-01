"""Suite de demo con cuatro "personalidades". Las flaky dependen de `random`, que Apoptosis siembra por intento."""
import random

_calls = {"n": 0}


def test_estable():
    assert 1 + 1 == 2


def test_roto_de_verdad():
    """Falla SIEMPRE: es un bug real, no flakiness. Apoptosis NO debe cuarentenarlo."""
    assert "a" == "b"


def test_flaky_moneda_30pct():
    assert random.random() > 0.30, "timeout simulado esperando al servicio"


def test_flaky_estado_compartido():
    """Falla cada 3.ª ejecución: típico de estado que se filtra entre tests."""
    _calls["n"] += 1
    assert _calls["n"] % 3 != 0, "estado compartido contaminado"


def test_estable_con_calculo():
    assert sum(range(10)) == 45


def test_flaky_raro_8pct():
    """Falla poco: suele quedar como 'sospechoso' (vigilado) sin llegar a morir."""
    assert random.random() > 0.08, "carrera en la cola de mensajes"
