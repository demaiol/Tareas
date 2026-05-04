#!/bin/zsh
set -euo pipefail

BASE_DIR="/Users/leonardodemaio/Library/Mobile Documents/com~apple~CloudDocs/Codex Local/Tareas"
LOCAL_DIR="$BASE_DIR/.local"
VENV_ACTIVATE="$BASE_DIR/.venv/bin/activate"

APP_LOG="$LOCAL_DIR/app-8501.log"
APP_PID_FILE="$LOCAL_DIR/app-8501.pid"
REPORT_LOG="$LOCAL_DIR/report-8502.log"
REPORT_PID_FILE="$LOCAL_DIR/report-8502.pid"
USERS_LOG="$LOCAL_DIR/users-8503.log"
USERS_PID_FILE="$LOCAL_DIR/users-8503.pid"
DEBTS_LOG="$LOCAL_DIR/debts-8504.log"
DEBTS_PID_FILE="$LOCAL_DIR/debts-8504.pid"

mkdir -p "$LOCAL_DIR"

start_service() {
  local port="$1"
  local target="$2"
  local log_file="$3"
  local pid_file="$4"

  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port already in use. Service for $target appears to be running."
    return
  fi

  source "$VENV_ACTIVATE"
  nohup streamlit run "$target" --server.address 0.0.0.0 --server.port "$port" --server.headless true > "$log_file" 2>&1 &
  local pid=$!
  echo "$pid" > "$pid_file"
  echo "Started $target on port $port (PID $pid)"
}

start_service 8501 "$BASE_DIR/app.py" "$APP_LOG" "$APP_PID_FILE"
start_service 8502 "$BASE_DIR/report_app.py" "$REPORT_LOG" "$REPORT_PID_FILE"
start_service 8503 "$BASE_DIR/users_admin_app.py" "$USERS_LOG" "$USERS_PID_FILE"
start_service 8504 "$BASE_DIR/debts_app.py" "$DEBTS_LOG" "$DEBTS_PID_FILE"

echo "Done. URLs:"
echo "- Gestion: http://localhost:8501"
echo "- Reporte: http://localhost:8502"
echo "- Usuarios: http://localhost:8503"
echo "- Deudas: http://localhost:8504"
