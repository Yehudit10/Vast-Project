import pathlib, sys, csv

# Ensure project root on path
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from mqtt_ingest import app

def test_ensure_csv_and_write(tmp_path):
    path = tmp_path / "latency.csv"
    app.ensure_csv(str(path))
    # header exists
    with open(path) as f:
        header = f.readline().strip().split(",")
    assert header == app._csv_header

    # append a row
    app.write_csv_row(str(path), [1, 2, 1, 100, "k"])
    with open(path) as f:
        rows = list(csv.reader(f))
    assert rows[1] == ["1", "2", "1", "100", "k"]

def test_on_message_enqueues(monkeypatch):
    events = []
    class FakeQueue:
        def put(self, item): events.append(item)
    monkeypatch.setattr(app, "q_in", FakeQueue())

    class Msg:
        topic = "MQTT/imagery/camX/1730000000000/image_jpeg/a.jpg"
        payload = b"abc"

    app.on_message(None, None, Msg)
    assert len(events) == 1
    t, payload, zero = events[0]
    assert "imagery" in t
    assert payload == b"abc"
    assert zero == 0
