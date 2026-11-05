# Match the Python version required by pyproject.toml so uv does not install a
# second interpreter inside the image.
FROM python:3.14-slim

# Install necessary system dependencies for Chrome/Selenium.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        chromium \
        chromium-driver \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV UV_NO_CACHE=1
ENV UV_COMPILE_BYTECODE=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# This layer is reused until dependency metadata changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache

COPY . ./

EXPOSE 5000

CMD ["uv", "run", "--no-sync", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5000"]
