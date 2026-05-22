# Agent Guide

This repository is a FastAPI-based Zerodha Kite options trading bot. It runs a
live dashboard, refreshes Kite access tokens through Selenium login flows, keeps
background monitoring threads alive, and can place or exit real market orders.
Treat code changes as production trading changes unless explicitly told
otherwise.

## Project Snapshot

- `app.py` is the main FastAPI application used by local and Docker runs.
- `main.py` is a small health/demo FastAPI app and is not the primary runtime.
- `Core/Delta_IV.py` owns KiteTicker/WebSocket data, option-chain state, IV, and
  delta calculations.
- `Core/Monitor.py` owns live position monitoring, P&L, stop loss, exit, and leg
  shift behavior.
- `Core/shared_resources.py` stores shared monitoring state.
- `Auth/login.py` is the local Selenium/TOTP login flow.
- `Auth/login_prod.py` is the production/Lightsail Selenium login flow.
- `templates/` and `static/` contain the dashboard UI.
- `Dockerfile` and `docker-compose.yml` are used for Docker/Lightsail
  deployment.

## Environment And Secrets

Do not commit credentials or generated tokens.

Expected local files:

- `.env.local` for local development.
- `.env.lightsail` for Lightsail/Docker deployment.
- `Cred/Cred_kite_PREM.ini` for Kite and Telegram credentials.
- `Cred/access_token.txt` for the current Kite access token.

`app.py` chooses the env file from `ENV`, or falls back to `.env.local` /
`.env.lightsail` if present. Missing env files intentionally stop startup.

## Common Commands

Install dependencies:

```bash
uv sync
```

Run locally:

```bash
uv run uvicorn app:app --reload
```

Run the primary app on the same port used by Docker:

```bash
uv run uvicorn app:app --host 0.0.0.0 --port 5000
```

Run with Docker:

```bash
docker-compose up --build
```

Run detached, suitable for a cron job:

```bash
docker-compose up -d
```

There is no formal test suite in the current repo. For syntax-level validation,
prefer:

```bash
uv run python -m compileall app.py main.py Auth Core
```

## Coding Guidelines

- Preserve the existing module boundaries. API orchestration belongs in
  `app.py`; market data and Greeks belong in `Core/Delta_IV.py`; order and
  monitoring behavior belongs in `Core/Monitor.py`.
- Be careful with global state in `app.py`. Several endpoint actions are guarded
  by locks to prevent duplicate exits, stop losses, cancellations, and shifts.
- Keep FastAPI response shapes stable unless the frontend is updated at the same
  time.
- Use Pydantic models for new request bodies.
- Keep blocking or long-running trading work out of request handlers where
  possible. Existing behavior uses daemon threads for continuous monitoring.
- When editing dashboard behavior, update the matching template and static JS
  together.
- Avoid broad refactors during market-sensitive changes. Small, reversible
  changes are easier to reason about and safer to deploy.

## Trading Safety Rules

- Never run live order-placement, exit, stop-loss, or shift flows just to test a
  code change.
- Do not call endpoints such as `/manual_exit`, `/manual_stoploss`,
  `/manual_cancel_sl`, `/shift_legs`, or `/exit_selected_legs` against a live
  session unless the user explicitly asks for it.
- Do not modify credential paths, token refresh behavior, order sequencing, or
  product/exchange normalization casually.
- For changes touching `Core/Monitor.py` or order endpoints, inspect both the API
  handler and the underlying Kite call path before editing.
- Prefer dry validation, unit-level checks, or mocked Kite clients for risky
  paths.

## Deployment Notes

- Docker runs `uv run uvicorn app:app --host 0.0.0.0 --port 5000`.
- `docker-compose.yml` uses host networking, `.env.lightsail`, and
  `TZ=Asia/Kolkata`.
- Cron should call Docker Compose directly from the project directory, for
  example `docker-compose up -d`.
- Selenium in Docker depends on Chromium paths:
  `CHROME_BIN=/usr/bin/chromium` and
  `CHROMEDRIVER_PATH=/usr/bin/chromedriver`.

## Review Checklist

Before handing changes back:

- Confirm no secrets, access tokens, logs, or credential files were added.
- Run `uv run python -m compileall app.py main.py Auth Core` when Python files
  changed.
- For frontend changes, verify the page still loads and the relevant endpoint
  contract is unchanged or updated consistently.
- For Docker/deployment changes, check that `Dockerfile`, `docker-compose.yml`,
  and cron usage still agree on the app entry point and port.
- Call out any validation that could not be run because it requires a live Kite
  session or credentials.
