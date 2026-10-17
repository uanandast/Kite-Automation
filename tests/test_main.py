from fastapi.testclient import TestClient

from main import app


def test_root_status_ok():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "message": "Hello from Kite FastAPI in Docker!",
    }
