FROM python:3.11-slim

# Install necessary system dependencies for Chrome/Selenium and general utilities
RUN apt-get update && apt-get install -y\
    wget \
    gnupg \
    unzip \
    curl \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for Chrome
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy pyproject.toml and uv.lock if it exists
COPY pyproject.toml /app/
# We copy uv.lock if we have one, but we will run uv sync anyway
COPY . /app/

# Install the application dependencies using uv
RUN uv sync --frozen || uv sync

# Expose port 5000 for FastAPI
EXPOSE 5000

# Command to run the application using uvicorn
CMD ["uv", "run", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5000"]
