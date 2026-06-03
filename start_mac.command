#!/bin/bash
# =============================================================================
# start_mac.command  --  one-click launcher for the local (Ollama) stack on a Mac
#
# Double-click this file in Finder. It will:
#   1. Make sure Ollama is running.
#   2. Free port 8000 if a stale server is holding it.
#   3. Open a Terminal tab for the environment (web) server, on the network.
#   4. Open a Terminal tab for the simulation backend (reverie.py).
#
# You still answer reverie's prompts in the backend tab (forked sim name, new
# sim name, then `run 2200`). To stop everything: press Ctrl+C in each tab, or
# just close the tabs.
#
# First time only, if double-click does nothing, make it executable once:
#   chmod +x start_mac.command
# =============================================================================

# Resolve the repo root (this script lives at the root).
REPO="$(cd "$(dirname "$0")" && pwd)"

# Your Mac's LAN IP, so we can print the tablet URL (falls back en0 -> en1).
IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)"
[ -z "$IP" ] && IP="<your-mac-ip>"

# 1. Ensure Ollama is up (start the app, or fall back to `ollama serve`).
if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
  open -a Ollama >/dev/null 2>&1 || nohup ollama serve >/tmp/ollama_serve.log 2>&1 &
  sleep 2
fi

# 2. Free port 8000 in case a previous frontend server is still holding it.
lsof -ti:8000 | xargs kill -9 >/dev/null 2>&1

# 3. Frontend (web) server -- listens on the network so a tablet can connect.
osascript <<EOF
tell application "Terminal"
  activate
  do script "cd '$REPO/environment/frontend_server' && source '$REPO/venv/bin/activate' && export DJANGO_ALLOWED_HOSTS='*' && echo '== ENVIRONMENT SERVER ==' && echo 'On this Mac: http://localhost:8000/simulator_home' && echo 'On tablet:   http://$IP:8000/simulator_home' && echo '' && python manage.py runserver 0.0.0.0:8000"
end tell
EOF

# 4. Backend (reverie) -- interactive; answer the prompts here.
osascript <<EOF
tell application "Terminal"
  activate
  do script "cd '$REPO/reverie/backend_server' && source '$REPO/venv/bin/activate' && echo '== SIMULATION BACKEND ==' && echo 'At the prompts: base_the_ville_isabella_maria_klaus / a new name / run 2200' && echo '' && python reverie.py"
end tell
EOF
