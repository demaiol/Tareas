#!/bin/zsh
set -euo pipefail

BASE_DIR="/Users/leonardodemaio/Library/Mobile Documents/com~apple~CloudDocs/Codex Local/Tareas"
LOCAL_DIR="$BASE_DIR/.local"

stop_by_pid_file() {
  local pid_file="$1"
  if [ -f "$pid_file" ]; then
    local pid
    pid=$(cat "$pid_file")
    if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" || true
      echo "Stopped PID $pid"
    fi
    rm -f "$pid_file"
  fi
}

stop_by_port() {
  local port="$1"
  local pids
  pids=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "$pids" | xargs kill || true
    echo "Stopped processes on port $port"
  fi
}

stop_by_pid_file "$LOCAL_DIR/app-8501.pid"
stop_by_pid_file "$LOCAL_DIR/report-8502.pid"

stop_by_port 8501
stop_by_port 8502

echo "Done. Services are down."
