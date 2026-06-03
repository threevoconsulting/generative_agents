#!/bin/bash
# =============================================================================
# start_mac.command  --  one-click launcher for the local (Ollama) stack on a Mac
#
# Double-click this file in Finder. It will:
#   1. Ask whether to open in View or Play mode.
#   2. Make sure Ollama is running.
#   3. Free port 8000 if a stale server is holding it.
#   4. Open a Terminal tab for the environment (web) server, on the network.
#   5. Open a Terminal tab for the simulation backend (reverie.py).
#   6. Wait for the web server, then open Firefox to the town.
#
# You still pick a base sim from reverie's menu in the backend tab, then type
# e.g. `run 2200`. To stop everything: Ctrl+C in each tab, or close them.
#
# First time only, if double-click does nothing, make it executable once:
#   chmod +x start_mac.command
# =============================================================================

# Resolve the repo root (this script lives at the root).
REPO="$(cd "$(dirname "$0")" && pwd)"

# Your Mac's LAN IP, so we can print the tablet URL (falls back en0 -> en1).
IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)"
[ -z "$IP" ] && IP="<your-mac-ip>"

# 0. Ask which mode to open the browser in.
echo "Open the town in:"
echo "  [1] View mode  -- watch the agents          (default)"
echo "  [2] Play mode  -- walk around and talk to them"
read -r -p "Choose [1]: " MODE
if [ "$MODE" = "2" ]; then
  read -r -p "Your player name [Alex]: " PNAME
  [ -z "$PNAME" ] && PNAME="Alex"
  URL="http://localhost:8000/simulator_play?name=$PNAME"
else
  URL="http://localhost:8000/simulator_home"
fi

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
  do script "cd '$REPO/environment/frontend_server' && source '$REPO/venv/bin/activate' && export DJANGO_ALLOWED_HOSTS='*' && echo '== ENVIRONMENT SERVER ==' && echo 'View:   http://localhost:8000/simulator_home' && echo 'Play:   http://localhost:8000/simulator_play?name=Alex' && echo 'Tablet: http://$IP:8000/simulator_home' && echo '' && python manage.py runserver 0.0.0.0:8000"
end tell
EOF

# 4. Backend (reverie) -- interactive; pick a base from the menu here.
osascript <<EOF
tell application "Terminal"
  activate
  do script "cd '$REPO/reverie/backend_server' && source '$REPO/venv/bin/activate' && echo '== SIMULATION BACKEND ==' && echo 'Pick a base from the menu, accept the run name, then type:  run 2200' && echo '' && python reverie.py"
end tell
EOF

# 5. Wait for the web server to answer, then open the browser to the town.
echo ""
echo "Waiting for the web server to start..."
for i in $(seq 1 40); do
  if curl -s -o /dev/null http://localhost:8000/; then break; fi
  sleep 1
done
echo "Opening $URL"
open -a Firefox "$URL" 2>/dev/null || open "$URL"

echo ""
echo "If the page says 'start the backend first', it's just early -- pick a sim"
echo "in the backend tab, type 'run 2200', then reload the browser (Cmd+Shift+R)."
