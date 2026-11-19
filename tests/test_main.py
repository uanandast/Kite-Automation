from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from webapp.auth import DashboardAuthMiddleware
from webapp.routes import create_router
from webapp.settings import Settings
from webapp.state import RuntimeState


class FakeMonitor:
    pnl_total = 125.5
    Current_pos_credit = 42.0
    available_margin = 9_500.0

    def __init__(self):
        self.kite = SimpleNamespace(positions=lambda: {"net": [{"tradingsymbol": "NIFTY"}]})
        self.shift_calls = []
        self.exit_calls = []
        self.recommended_order_calls = []

    def get_open_option_positions(self):
        return [{"tradingsymbol": "NIFTY24OCT25000CE"}]

    def shift_selected_legs(self, legs, shift):
        self.shift_calls.append((legs, shift))
        return {"requested": len(legs), "succeeded": len(legs), "failed": 0}

    def exit_selected_legs(self, legs):
        self.exit_calls.append(legs)
        return {"requested": len(legs), "succeeded": len(legs), "failed": 0}

    def place_recommended_iron_condor(self, legs, quantity, exchange):
        self.recommended_order_calls.append((legs, quantity, exchange))
        return {"hedges_placed": 2, "shorts_placed": 2, "orders": []}


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


@pytest.fixture
def secured_client(state):
    settings = Settings(
        environment="local",
        dashboard_username="dashboard-user",
        dashboard_password="dashboard-password",
        session_secret="a-secure-test-session-secret-that-is-long-enough",
    )
    app = FastAPI()
    app.state.settings = settings
    app.add_middleware(DashboardAuthMiddleware, settings=settings)
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
    app.include_router(create_router(state, Jinja2Templates(directory="templates")))
    return TestClient(app)


def test_dashboard_root_returns_html(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Option Chain Dashboard" in response.text


def test_dashboard_requires_login_and_allows_a_valid_session(secured_client):
    unauthenticated = secured_client.get("/", headers={"accept": "text/html"})
    assert unauthenticated.status_code == 200
    assert unauthenticated.url.path == "/login"

    invalid = secured_client.post(
        "/login", data={"username": "dashboard-user", "password": "wrong"}
    )
    assert invalid.status_code == 401

    login = secured_client.post(
        "/login",
        data={"username": "dashboard-user", "password": "dashboard-password"},
    )
    assert login.status_code == 200
    assert login.url.path == "/"
    assert "Option Chain Dashboard" in login.text

    assert secured_client.get("/pnl").status_code == 200
    logout = secured_client.post("/logout")
    assert logout.status_code == 200
    assert logout.url.path == "/login"
    assert secured_client.get("/pnl").status_code == 401


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


def test_access_request_sends_admin_notification(client, monkeypatch):
    messages = []
    monkeypatch.setattr("webapp.routes.send_telegram", messages.append)

    response = client.post(
        "/request-access",
        data={
            "name": "Analyst User",
            "email": "analyst@example.com",
            "reason": "Monitor the trading dashboard",
        },
    )

    assert response.status_code == 200
    assert "Your request was sent" in response.text
    assert len(messages) == 1
    assert "analyst@example.com" in messages[0]


def test_entra_settings_parse_allowlist():
    settings = Settings(
        environment="production",
        dashboard_username="",
        dashboard_password="",
        session_secret="a-secure-test-session-secret-that-is-long-enough",
        entra_tenant_id="tenant-id",
        entra_client_id="client-id",
        entra_client_secret="client-secret",
        entra_redirect_uri="https://uanandast.duckdns.org/auth/entra/callback",
        entra_allowed_emails="Admin@example.com, analyst@example.com ",
    )

    assert settings.entra_enabled
    assert settings.allowed_entra_emails == {"admin@example.com", "analyst@example.com"}


def test_entra_settings_public_client():
    settings = Settings(
        environment="production",
        dashboard_username="",
        dashboard_password="",
        session_secret="a-secure-test-session-secret-that-is-long-enough",
        entra_tenant_id="consumers",
        entra_client_id="client-id",
        entra_client_secret="",
        entra_redirect_uri="https://uanandast.duckdns.org/auth/entra/callback",
        entra_allowed_emails="user@example.com",
        entra_public_client=True,
    )
    assert settings.entra_enabled

    from msal import ConfidentialClientApplication, PublicClientApplication
    from webapp.entra import create_client

    client = create_client(settings)
    assert isinstance(client, PublicClientApplication)

    conf_settings = Settings(
        environment="production",
        dashboard_username="",
        dashboard_password="",
        session_secret="a-secure-test-session-secret-that-is-long-enough",
        entra_tenant_id="consumers",
        entra_client_id="client-id",
        entra_client_secret="client-secret",
        entra_redirect_uri="https://uanandast.duckdns.org/auth/entra/callback",
        entra_allowed_emails="user@example.com",
        entra_public_client=False,
    )
    conf_client = create_client(conf_settings)
    assert isinstance(conf_client, ConfidentialClientApplication)


def test_login_page_shows_microsoft_sso_button_when_entra_is_enabled(state):
    settings = Settings(
        environment="local",
        dashboard_username="",
        dashboard_password="",
        session_secret="a-secure-test-session-secret-that-is-long-enough",
        entra_tenant_id="tenant-id",
        entra_client_id="client-id",
        entra_client_secret="client-secret",
        entra_redirect_uri="https://example.com/auth/entra/callback",
    )
    app = FastAPI()
    app.state.settings = settings
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
    app.include_router(create_router(state, Jinja2Templates(directory="templates")))

    response = TestClient(app).get("/login")

    assert response.status_code == 200
    assert "Continue with Microsoft" in response.text
    assert 'href="/auth/entra/login"' in response.text


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


def test_pnl_history_returns_current_server_session_samples(client, state):
    state.record_pnl_sample("nifty", 1_700_000_000_000, 125.5, 80.0)

    response = client.get("/pnl/history")

    assert response.status_code == 200
    assert response.json() == {
        "index": "nifty",
        "samples": [
            {
                "timestamp": 1_700_000_000_000,
                "net_pnl": 125.5,
                "straddle_price": 80.0,
            }
        ],
    }


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


def test_place_recommended_order_uses_server_legs_and_lot_quantity(client, state):
    state.latest_iron_condor_data["legs"] = {
        "hedge_pe": {"instrument_token": "NIFTY24OCT24000PE"},
        "hedge_ce": {"instrument_token": "NIFTY24OCT26000CE"},
        "short_pe": {"instrument_token": "NIFTY24OCT24500PE"},
        "short_ce": {"instrument_token": "NIFTY24OCT25500CE"},
    }

    invalid = client.post("/place_recommended_order", json={"quantity": 66})
    response = client.post("/place_recommended_order", json={"quantity": 65})

    assert invalid.status_code == 400
    assert invalid.json()["detail"] == "Quantity must be a multiple of 65 for NIFTY"
    assert response.status_code == 200
    assert response.json()["message"] == "Bought 2 hedge legs, then sold 2 short legs"
    assert state.monitor_module.recommended_order_calls == [
        (state.latest_iron_condor_data["legs"], 65, "NFO")
    ]


def test_sanitize_for_json_converts_nan_and_numpy_types():
    from webapp.serializers import sanitize_for_json

    data = {
        "nan_val": float("nan"),
        "inf_val": float("inf"),
        "np_nan": np.float64(np.nan),
        "np_float": np.float64(12.34),
        "np_int": np.int64(42),
        "np_bool": np.bool_(True),
        "nested": {
            "legs": {
                "hedge_pe": {
                    "delta": np.float64(np.nan),
                    "ltp": 0.0,
                }
            },
            "chain": [
                {"delta": np.float64(np.nan), "iv": 0.25},
                {"delta": 0.5, "iv": float("inf")},
            ],
        },
    }

    sanitized = sanitize_for_json(data)
    assert sanitized["nan_val"] is None
    assert sanitized["inf_val"] is None
    assert sanitized["np_nan"] is None
    assert sanitized["np_float"] == 12.34
    assert isinstance(sanitized["np_float"], float)
    assert sanitized["np_int"] == 42
    assert isinstance(sanitized["np_int"], int)
    assert sanitized["np_bool"] is True
    assert sanitized["nested"]["legs"]["hedge_pe"]["delta"] is None
    assert sanitized["nested"]["legs"]["hedge_pe"]["ltp"] == 0.0
    assert sanitized["nested"]["chain"][0]["delta"] is None
    assert sanitized["nested"]["chain"][0]["iv"] == 0.25
    assert sanitized["nested"]["chain"][1]["iv"] is None


def test_option_data_handles_nan_and_numpy_floats_without_error(client, state):
    import numpy as np

    state.latest_iron_condor_data = {
        "legs": {
            "hedge_pe": {
                "instrument_token": "NIFTY24OCT23000PE",
                "strike": 23000.0,
                "type": "PE",
                "ltp": 0.0,
                "delta": np.float64(np.nan),
            }
        },
        "net_delta": np.float64(np.nan),
        "chain": [],
        "spot_price": np.float64(24500.0),
    }

    response = client.get("/option_data")
    assert response.status_code == 200
    body = response.json()
    assert body["legs"]["hedge_pe"]["delta"] is None
    assert body["legs"]["hedge_pe"]["ltp"] == 0.0
    assert body["net_delta"] is None
    assert body["spot_price"] == 24500.0
