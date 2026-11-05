from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from webapp.routes import create_router
from webapp.state import RuntimeState


class FakeMonitor:
    pnl_total = 125.5
    Current_pos_credit = 42.0
    available_margin = 9_500.0

    def __init__(self):
        self.kite = SimpleNamespace(positions=lambda: {"net": [{"tradingsymbol": "NIFTY"}]})
        self.shift_calls = []
        self.exit_calls = []

    def get_open_option_positions(self):
        return [{"tradingsymbol": "NIFTY24OCT25000CE"}]

    def shift_selected_legs(self, legs, shift):
        self.shift_calls.append((legs, shift))
        return {"requested": len(legs), "succeeded": len(legs), "failed": 0}

    def exit_selected_legs(self, legs):
        self.exit_calls.append(legs)
        return {"requested": len(legs), "succeeded": len(legs), "failed": 0}


@pytest.fixture
def state():
    monitor = FakeMonitor()
    return RuntimeState(
        latest_iron_condor_data={"strangle_credit": 80.0, "spot_price": 24_500.0},
        monitor_module=monitor,
        get_selected_index=lambda: "nifty",
        get_available_indices=lambda: ["nifty", "banknifty"],
        get_previous_day_close=lambda: (24_400.0, "NIFTY 50"),
        margin=10_000.0,
        previous_day_close=24_400.0,
        name="NIFTY 50",
    )


@pytest.fixture
def client(state):
    app = FastAPI()
    app.include_router(create_router(state, Jinja2Templates(directory="templates")))
    return TestClient(app)


def test_dashboard_root_returns_html(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Option Chain Dashboard" in response.text


def test_option_data_includes_runtime_and_market_state(client):
    response = client.get("/option_data")

    assert response.status_code == 200
    assert response.json() == {
        "strangle_credit": 80.0,
        "spot_price": 24_500.0,
        "previous_close": 24_400.0,
        "symbol": "NIFTY 50",
        "selected_index": "nifty",
    }


def test_indices_returns_available_and_selected_values(client):
    response = client.get("/indices")

    assert response.status_code == 200
    assert response.json() == {"available": ["nifty", "banknifty"], "selected": "nifty"}


def test_indices_returns_503_before_runtime_is_initialized():
    app = FastAPI()
    app.include_router(create_router(RuntimeState(), Jinja2Templates(directory="templates")))

    response = TestClient(app).get("/indices")

    assert response.status_code == 503
    assert response.json()["detail"] == "Kite runtime not initialized"


def test_set_index_normalizes_value_and_resets_cached_data(client, state):
    selected_indexes = []
    state.set_selected_index = lambda value: selected_indexes.append(value) or value

    response = client.post("/set_index", json={"index": "  BANKNIFTY "})

    assert response.status_code == 200
    assert response.json() == {
        "message": "Index switched to BANKNIFTY",
        "selected": "banknifty",
        "symbol": "NIFTY 50",
    }
    assert selected_indexes == ["banknifty"]
    assert state.latest_iron_condor_data == {}


def test_pnl_returns_monitor_and_market_values(client):
    response = client.get("/pnl")

    body = response.json()
    assert response.status_code == 200
    assert body["net_pnl"] == 125.5
    assert body["straddle_price"] == 80.0
    assert body["Current_pos_credit"] == 42.0
    assert body["margin"] == 10_000.0
    assert body["available_margin"] == 9_500.0
    assert body["nifty_value"] == 24_500.0
    assert body["timestamp"].endswith("+00:00")


def test_shift_legs_rejects_missing_or_zero_shift(client):
    assert client.post("/shift_legs", json={"legs": [], "shift": 1}).status_code == 400
    assert client.post("/shift_legs", json={"legs": ["NIFTY"], "shift": 0}).status_code == 400


def test_shift_legs_normalizes_input_before_calling_monitor(client, state):
    response = client.post(
        "/shift_legs",
        json={
            "legs": [
                "  NIFTY24OCT25000CE  ",
                {"tradingsymbol": "NIFTY24OCT25000PE", "exchange": "nfo", "product": "NRML", "new_qty": "50"},
            ],
            "shift": 100,
        },
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Shifted 2/2 legs"
    assert state.monitor_module.shift_calls == [
        (
            [
                {"tradingsymbol": "NIFTY24OCT25000CE"},
                {"tradingsymbol": "NIFTY24OCT25000PE", "exchange": "NFO", "product": "NRML", "new_qty": 50},
            ],
            100,
        )
    ]


def test_exit_selected_legs_rejects_invalid_quantity_and_calls_monitor(client, state):
    invalid = client.post(
        "/shift_legs",
        json={"legs": [{"tradingsymbol": "NIFTY", "new_qty": "not-a-number"}], "shift": 50},
    )
    response = client.post("/exit_selected_legs", json={"legs": [" NIFTY24OCT25000CE "]})

    assert invalid.status_code == 400
    assert invalid.json()["detail"] == "Invalid new_qty for NIFTY"
    assert response.status_code == 200
    assert response.json()["message"] == "Exited 1/1 selected legs"
    assert state.monitor_module.exit_calls == [[{"tradingsymbol": "NIFTY24OCT25000CE"}]]
