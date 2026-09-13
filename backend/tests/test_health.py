from fastapi.testclient import TestClient


def test_live_and_ready_probes(client: TestClient):
    live = client.get("/livez")
    ready = client.get("/readyz")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}
