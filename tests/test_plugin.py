import pytest

from apoptosis.store import Store

# Flaky determinista: falla cuando la semilla del intento es múltiplo de 3 (con --apoptosis-seed=0 y 10 runs: 0,3,6,9).
SUITE = """
import os
def test_ok():
    assert True

def test_roto():
    assert False, "bug real"

def test_flaky(apoptosis_seed):
    if not os.environ.get("FIXED"):
        assert apoptosis_seed % 3 != 0, "timeout simulado"
"""
SCAN = ("--apoptosis-runs=10", "--apoptosis-seed=0", "-p", "no:cacheprovider")


def state(pytester):
    return Store(pytester.path / ".apoptosis").state()


def test_es_inerte_sin_flags(pytester):
    pytester.makepyfile(SUITE)
    r = pytester.runpytest("-p", "no:cacheprovider")
    r.assert_outcomes(passed=1, failed=2)
    assert not (pytester.path / ".apoptosis").exists()


def test_scan_mata_al_flaky_pero_no_al_roto(pytester):
    pytester.makepyfile(SUITE)
    r = pytester.runpytest(*SCAN, "--apoptosis-no-issues")
    r.assert_outcomes(passed=1, failed=1, skipped=1)            # el roto SIGUE fallando: es un bug real
    r.stdout.fnmatch_lines(["*cuarentena: test_scan_mata*test_flaky*"])
    s = state(pytester)
    assert [n for n, t in s.tests.items() if t.quarantined] == [next(n for n in s.tests if n.endswith("test_flaky"))]
    assert not s.tests[next(n for n in s.tests if n.endswith("test_roto"))].quarantined
    assert (pytester.path / ".apoptosis" / "quarantine.json").exists()
    assert list((pytester.path / ".apoptosis" / "issues").glob("*.md"))      # issue local aunque no haya GitHub


def test_la_siguiente_corrida_salta_la_cuarentena(pytester):
    pytester.makepyfile(SUITE)
    pytester.runpytest(*SCAN, "--apoptosis-no-issues")
    r = pytester.runpytest("--apoptosis", "--apoptosis-no-issues", "-rs", "-p", "no:cacheprovider")
    r.assert_outcomes(passed=1, failed=1, skipped=1)
    r.stdout.fnmatch_lines(["*apoptosis: en cuarentena desde*"])


def test_curacion_reintegra_tras_10_pasadas_seguidas(pytester, monkeypatch):
    pytester.makepyfile(SUITE)
    pytester.runpytest(*SCAN, "--apoptosis-no-issues")
    monkeypatch.setenv("FIXED", "1")                              # "alguien arregló el test"
    r = pytester.runpytest("--apoptosis-heal", "--apoptosis-seed=0", "--apoptosis-no-issues", "-p", "no:cacheprovider")
    r.assert_outcomes(passed=1)
    r.stdout.fnmatch_lines(["*reintegrado*test_flaky*10 pasadas*"])
    assert not any(t.quarantined for t in state(pytester).tests.values())
    r = pytester.runpytest("--apoptosis", "--apoptosis-no-issues", "-p", "no:cacheprovider")
    r.assert_outcomes(passed=2, failed=1)                         # vuelve al pipeline


HEAL_SUITE = """
import os
def test_t(apoptosis_seed):
    if os.environ.get("MODE") == "heal":
        assert apoptosis_seed != 4, "vuelve a fallar"
    else:
        assert apoptosis_seed % 3 != 0
"""


def test_un_fallo_reinicia_la_racha_y_se_acumula_entre_ejecuciones(pytester, monkeypatch):
    pytester.makepyfile(HEAL_SUITE)
    pytester.runpytest(*SCAN, "--apoptosis-no-issues")
    monkeypatch.setenv("MODE", "heal")
    heal = ("--apoptosis-heal", "--apoptosis-seed=0", "--apoptosis-no-issues", "-p", "no:cacheprovider", "-rs")
    r = pytester.runpytest(*heal)                                 # semillas 0..3 pasan, la 4 falla → racha a 0
    r.assert_outcomes(skipped=1)
    r.stdout.fnmatch_lines(["*sigue inestable, racha reiniciada*"])
    rec = next(iter(state(pytester).tests.values()))
    assert rec.quarantined and rec.heal_streak == 0 and rec.heal_attempts == 5
    r = pytester.runpytest(*heal)                                 # semillas 5..14: diez pasadas seguidas
    r.assert_outcomes(passed=1)
    assert not next(iter(state(pytester).tests.values())).quarantined


def test_curacion_sin_nada_en_cuarentena_no_es_error(pytester):
    pytester.makepyfile("def test_a(): pass")
    r = pytester.runpytest("--apoptosis-heal", "-p", "no:cacheprovider")
    assert r.ret == 0


def test_un_cambio_de_estado_estable_no_es_flakiness(pytester):
    pytester.makepyfile("def test_a(apoptosis_seed):\n    assert apoptosis_seed < 6\n")   # PPPPPPFFFF
    r = pytester.runpytest(*SCAN, "--apoptosis-no-issues")
    r.assert_outcomes(failed=1)                                   # regresión real: sigue en rojo y no se cuarentena
    assert not next(iter(state(pytester).tests.values())).quarantined


def test_marca_immune(pytester):
    pytester.makepyfile("import pytest\n@pytest.mark.apoptosis_immune\ndef test_a(apoptosis_seed):\n    assert apoptosis_seed % 3 != 0\n")
    r = pytester.runpytest(*SCAN, "--apoptosis-no-issues")
    r.assert_outcomes(failed=1)
    assert not next(iter(state(pytester).tests.values())).quarantined


def test_semillas_distintas_por_intento_y_random_sembrado(pytester):
    pytester.makepyfile("""
import random
def test_a(apoptosis_seed):
    open("out.txt", "a").write(f"{apoptosis_seed} {random.random():.6f}\\n")
""")
    pytester.runpytest("--apoptosis-runs=5", "--apoptosis-seed=10", "-p", "no:cacheprovider")
    seeds, values = zip(*(line.split() for line in (pytester.path / "out.txt").read_text().splitlines()))
    assert seeds == ("10", "11", "12", "13", "14") and len(set(values)) == 5


def test_los_fixtures_se_reconstruyen_en_cada_repeticion(pytester):
    pytester.makepyfile("""
import pytest
@pytest.fixture
def fresh():
    open("setups.txt", "a").write("s\\n"); yield []; open("setups.txt", "a").write("t\\n")
def test_a(fresh):
    assert fresh == []; fresh.append(1)   # si el fixture se reutilizara, el 2.º intento vería [1]
""")
    r = pytester.runpytest("--apoptosis-runs=4", "-p", "no:cacheprovider")
    r.assert_outcomes(passed=1)
    assert (pytester.path / "setups.txt").read_text() == "s\nt\n" * 4


def test_configuracion_por_ini(pytester):
    pytester.makeini("[pytest]\napoptosis_runs = 10\napoptosis_seed = 0\napoptosis_threshold = 0.75\n")
    pytester.makepyfile("def test_a(apoptosis_seed):\n    assert apoptosis_seed % 3 != 0\n")
    r = pytester.runpytest("-p", "no:cacheprovider")
    r.assert_outcomes(skipped=1)


def test_issues_en_github_ciclo_completo(pytester, monkeypatch, fake_github):
    pytester.makepyfile(SUITE)
    pytester.runpytest(*SCAN)                                     # 1) muere → se crea el issue
    create = fake_github.calls("POST", "/issues")
    assert len(create) == 1 and create[0]["auth"] == "Bearer tok_test"
    assert create[0]["body"]["labels"] == ["flaky-test", "apoptosis"]
    assert "test_flaky" in create[0]["body"]["title"] and "Historial" in create[0]["body"]["body"]
    rec = next(t for n, t in state(pytester).tests.items() if n.endswith("test_flaky"))
    assert rec.issue == {"number": 1, "url": "https://github.com/me/repo/issues/1", "open": True}

    sent = len(fake_github.requests)
    pytester.runpytest("--apoptosis", "-p", "no:cacheprovider")   # 2) corrida normal: silencio total hacia GitHub
    assert len(fake_github.requests) == sent                      # ni duplica, ni reabre, ni comenta de más

    monkeypatch.setenv("FIXED", "1")                              # 3) se cura → comentario + cierre
    pytester.runpytest("--apoptosis-heal", "--apoptosis-seed=0", "-p", "no:cacheprovider")
    assert fake_github.calls("PATCH", "/issues/1")[-1]["body"] == {"state": "closed"}
    assert "Reintegrado" in fake_github.calls("POST", "/issues/1/comments")[-1]["body"]["body"]

    monkeypatch.delenv("FIXED")                                   # 4) vuelve a romperse → reabre el MISMO issue
    pytester.runpytest(*SCAN)
    assert len(fake_github.calls("POST", "/issues")) == 1
    assert fake_github.calls("PATCH", "/issues/1")[-1]["body"] == {"state": "open"}
    assert "Volvió a la cuarentena" in fake_github.calls("POST", "/issues/1/comments")[-1]["body"]["body"]


def test_si_github_falla_la_corrida_sigue_y_reintenta_despues(pytester, fake_github):
    pytester.makepyfile(SUITE)
    fake_github.fail_with = 500
    r = pytester.runpytest(*SCAN)
    r.assert_outcomes(passed=1, failed=1, skipped=1)              # GitHub caído no rompe el pipeline
    r.stdout.fnmatch_lines(["*no pude sincronizar el issue*"])
    fake_github.fail_with = None
    pytester.runpytest("--apoptosis", "-p", "no:cacheprovider")   # el issue pendiente se crea en la siguiente sesión
    assert len([c for c in fake_github.calls("POST", "/issues") if c["body"] and "title" in c["body"]]) == 2  # 1 fallido + 1 ok
    assert next(t for n, t in state(pytester).tests.items() if n.endswith("test_flaky")).issue["open"]


def test_xdist(pytester):
    pytest.importorskip("xdist")
    pytester.makepyfile(SUITE)
    r = pytester.runpytest_subprocess("-n", "2", *SCAN, "--apoptosis-no-issues")
    r.assert_outcomes(passed=1, failed=1, skipped=1)
    assert sum(t.quarantined for t in state(pytester).tests.values()) == 1
