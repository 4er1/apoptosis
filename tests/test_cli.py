from apoptosis.cli import main
from apoptosis.store import Store


def seed_state(tmp_path):
    st = Store(tmp_path)
    ev = [{"type": "attempt", "nodeid": "t.py::flaky", "outcome": "pass" if i % 2 else "fail", "mode": "scan"} for i in range(12)]
    ev += [{"type": "attempt", "nodeid": "t.py::ok", "outcome": "pass", "mode": "scan"} for _ in range(12)]
    ev += [{"type": "kill", "nodeid": "t.py::flaky", "health": 0.0, "ts": "x"}]
    st.append(*ev)


def test_status_report_release_compact(tmp_path, capsys):
    seed_state(tmp_path)
    assert main(["status", "-d", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "quarantined" in out and "healthy" in out

    assert main(["report", "-d", str(tmp_path), "-o", str(tmp_path / "r.html")]) == 0
    html = (tmp_path / "r.html").read_text()
    assert "t.py::flaky" in html and "en cuarentena" in html

    assert main(["release", "-d", str(tmp_path), "t.py::flaky"]) == 0
    assert not Store(tmp_path).state().tests["t.py::flaky"].quarantined
    assert main(["release", "-d", str(tmp_path), "t.py::flaky"]) == 1       # ya no está en cuarentena

    assert main(["compact", "-d", str(tmp_path), "--keep", "5"]) == 0


def test_sin_dash_d_busca_apoptosis_hacia_arriba(tmp_path, monkeypatch, capsys):
    seed_state(tmp_path / ".apoptosis")
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    assert main(["status"]) == 0
    assert "t.py::flaky" in capsys.readouterr().out
