from apoptosis.store import State, Store


def att(nid, ok, mode="scan"):
    return {"type": "attempt", "nodeid": nid, "outcome": "pass" if ok else "fail", "mode": mode}


def test_append_y_load_ignoran_lineas_corruptas(tmp_path):
    st = Store(tmp_path)
    st.append(att("a", True), att("a", False))
    with open(st.path, "a") as f:
        f.write('{"type": "attempt", "nodeid": "a", "outc')  # proceso cortado a la mitad
    assert len(st.load()) == 2


def test_cuarentena_curacion_y_release():
    s = State.from_events([att("t", False), att("t", True), {"type": "kill", "nodeid": "t", "health": 0.2}])
    r = s.tests["t"]
    assert r.quarantined and r.heal_streak == 0
    for ok in (True, True, True, False, True):          # un fallo reinicia la racha
        s.apply(att("t", ok, "heal"))
    assert r.heal_streak == 1 and r.heal_attempts == 5
    s.apply({"type": "release", "nodeid": "t", "reason": "healed"})
    assert not r.quarantined and r.attempts == [] and r.heal_streak == 0   # historial reiniciado al reintegrar


def test_los_intentos_de_curacion_no_contaminan_la_salud():
    s = State.from_events([att("t", True), att("t", False, "heal")])
    assert s.tests["t"].outcomes() == [True]


def test_estado_del_issue():
    s = State.from_events([{"type": "issue", "nodeid": "t", "number": 3, "url": "u", "action": "created"}])
    assert s.tests["t"].issue["open"]
    s.apply({"type": "issue", "nodeid": "t", "number": 3, "action": "commented"})
    assert s.tests["t"].issue["open"]                     # un comentario no cambia el estado
    s.apply({"type": "issue", "nodeid": "t", "number": 3, "action": "closed"})
    assert not s.tests["t"].issue["open"]
    s.apply({"type": "issue", "nodeid": "t", "number": 3, "action": "reopened"})
    assert s.tests["t"].issue["open"]


def test_compactar_conserva_el_estado(tmp_path):
    st = Store(tmp_path)
    st.append(*[att("a", i % 2 == 0) for i in range(100)], att("b", True),
              {"type": "kill", "nodeid": "b", "health": 0.1, "ts": "x"},
              att("b", True, "heal"), att("b", True, "heal"),
              {"type": "issue", "nodeid": "b", "number": 9, "url": "u", "action": "created"})
    before = st.state()
    n0, n1 = st.compact(keep=30)
    after = st.state()
    assert n1 < n0
    assert after.tests["a"].outcomes() == before.tests["a"].outcomes()[-30:]
    assert after.tests["b"].quarantined and after.tests["b"].heal_streak == 2 and after.tests["b"].issue["open"]
