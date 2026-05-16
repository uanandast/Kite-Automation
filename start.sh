#!/bin/bash
# ============================================================
# start.sh — Startup wrapper for Kite Options Trading Bot
# Called by cron at 9:00 AM on weekdays
# ============================================================

set -e  # Exit immediately on any error

# Update this path to match your folder name on AWS
PROJECT_DIR="/home/ubuntu/kite_fast_api"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/docker_startup_$(date +%Y%m%d).log"

# --- Create logs directory if it doesn't exist ---
mkdir -p "$LOG_DIR"

# --- Log startup ---
echo "============================================================" >> "$LOG_FILE"
echo "[$(date)] Starting trading bot via Docker Compose..." >> "$LOG_FILE"
echo "============================================================" >> "$LOG_FILE"

# --- Change to project directory and run ---
cd "$PROJECT_DIR"

# Step 1: Pull latest changes from GitHub (optional but helpful)
# git pull origin main >> "$LOG_FILE" 2>&1

# Step 2: Ensure Docker Compose starts the app in detached mode
# We use --build to make sure any code changes are picked up
docker-compose up -d --build >> "$LOG_FILE" 2>&1

echo "[$(date)] Docker containers are running." >> "$LOG_FILE"
echo "Check logs with: docker-compose logs -f" >> "$LOG_FILE"
