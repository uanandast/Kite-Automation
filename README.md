# Kite Options Trading Bot (FastAPI + Docker)

A high-performance, real-time options trading automation system built for the Zerodha Kite Connect API. This project has been migrated from Flask to **FastAPI** to leverage asynchronous processing and ultra-low latency WebSocket monitoring.

## 🚀 Key Features

- **FastAPI Backend**: Non-blocking architecture for high-speed API responses and concurrent background tasks.
- **Real-Time WebSocket Optimization**: Synchronized with `KiteTicker` to provide zero-latency P&L monitoring and Delta calculations.
- **Dynamic Subscriptions**: Automatically subscribes open positions to the WebSocket stream on the fly.
- **Black-Scholes Engine**: Live calculation of Implied Volatility (IV) and Greeks (Delta) for precise strategy management.
- **Dockerized Environment**: Fully containerized with Selenium and Chromium support for automated login.
- **Responsive Dashboard**: Premium UI with live charts, P&L sparklines, and manual trade management (Shift Legs, Exit All, Place SL).
- **Telegram Integration**: Automated alerts for threshold breaches and trade executions.

## 🛠 Technology Stack

- **Backend**: FastAPI, Uvicorn, Python 3.11
- **Trading API**: KiteConnect, KiteTicker
- **Frontend**: HTML5, Vanilla CSS (Premium Glassmorphism Design), JavaScript
- **Deployment**: Docker, Docker Compose, AWS Lightsail
- **Utilities**: Pydantic, Selenium (for TOTP Login), Jinja2, NumPy, SciPy

## 📦 Installation & Setup

### 1. Prerequisites
- [uv](https://github.com/astral-sh/uv) (Fast Python package manager)
- Docker & Docker Compose (optional, for containerized run)

### 2. Environment Configuration
Create a `.env.local` file in the root directory:
```ini
ENV=local
OPEN_API_KEY=your_gemini_api_key
```
Ensure your `Cred/Cred_kite_PREM.ini` contains your Kite API credentials and BOT tokens.

### 3. Local Run (without Docker)
```bash
uv sync
uv run uvicorn app:app --reload
```

### 4. Running with Docker (Recommended)
```bash
docker-compose up --build
```

## ☁️ AWS Deployment (Lightsail)

1. **Clone the Repo**:
   ```bash
   git clone https://github.com/uanandast/Kite-Automation.git
   cd Kite-Automation
   ```
2. **Setup Credentials**:
   - Manually copy your `Cred/` folder and `.env.lightsail` to the server (these are ignored by git).
3. **Deploy / Start from the Project Directory**:
   ```bash
   docker-compose up -d
   ```

## 📂 Project Structure

- `app.py`: Main FastAPI application and lifecycle management.
- `Core/Monitor.py`: Active trade monitoring loop and P&L logic.
- `Core/Delta_IV.py`: WebSocket management and Black-Scholes calculations.
- `Auth/login.py`: Automated Selenium-based login and TOTP handling.
- `static/`: Frontend assets (CSS, JS, SVG).
- `templates/`: Jinja2 HTML templates.
- `Dockerfile` & `docker-compose.yml`: Containerization configuration.

## ⚠️ Security Notice
This repository contains a `.gitignore` to prevent sensitive credentials (`Cred/`, `.env`) from being uploaded. **Never** remove these entries or upload your actual API secrets to a public repository.

---
*Developed for high-speed algorithmic trading performance.*
