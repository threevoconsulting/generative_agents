# Install & Build Guide

This is the step-by-step guide for getting the (Claude + local-embedding) fork
running. Two paths are covered:

- **A. Local install** — for development on your own machine.
- **B. Docker / Synology / Portainer** — for deploying on a NAS (see also
  `DOCKER.md`).

The app is **two processes** that talk through a shared filesystem:
1. the **environment server** (Django + Phaser, serves the map at port 8000), and
2. the **simulation backend** (`reverie.py`, an interactive CLI that runs the agents).

Both must run at the same time.

---

## Prerequisites

- **Python 3.9** (the project targets 3.9.12; Django 2.2 is happiest on 3.8–3.9).
- **git**.
- An **Anthropic API key** (Claude) and outbound internet to `api.anthropic.com`.
- ~**3–4 GB free disk** (PyTorch, pulled in by local embeddings, is large).
- First run downloads the local embedding model `all-MiniLM-L6-v2` (~80 MB, once).

---

## A. Local install

### 1. Clone and branch
```bash
git clone <your-fork-url> generative_agents
cd generative_agents
git checkout claude/vigilant-hopper-FUvxV
```

### 2. Virtual environment
```bash
python3.9 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
python -m pip install --upgrade pip
```

### 3. Install dependencies (two files — one per server)
```bash
pip install -r requirements.txt                                   # backend (sim)
pip install -r environment/frontend_server/requirements.txt       # web server
```
> These are the pruned lists (analysis-only libraries removed). The backend
> install pulls in PyTorch via `sentence-transformers`; expect a few hundred MB.

### 4. Create the backend config
Create `reverie/backend_server/utils.py` (this file is gitignored — you create
it). Either copy the docker template or paste this:
```python
import os
key_owner = "Your Name"

# The key is read from the environment by llm_provider; export it in your shell:
#   export ANTHROPIC_API_KEY=sk-ant-...
# (You can also hard-code `anthropic_api_key = "..."` here instead.)

maze_assets_loc = "../../environment/frontend_server/static_dirs/assets"
env_matrix  = f"{maze_assets_loc}/the_ville/matrix"
env_visuals = f"{maze_assets_loc}/the_ville/visuals"
fs_storage      = "../../environment/frontend_server/storage"
fs_temp_storage = "../../environment/frontend_server/temp_storage"
collision_block_id = "32125"
debug = True
```
Then set the key:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### 5. (Optional) prepare the web server
The repo ships a populated `db.sqlite3`, so this is usually a no-op, but it is
safe to run:
```bash
cd environment/frontend_server
python manage.py migrate            # idempotent
cd ../..
```

### 6. Run it — two terminals (both with the venv active)

**Terminal 1 — environment server:**
```bash
cd environment/frontend_server
python manage.py runserver
```
Visit http://localhost:8000/ — you should see "environment server is up."

**Terminal 2 — simulation backend:**
```bash
cd reverie/backend_server
python reverie.py
#  > Enter the name of the forked simulation:  base_the_ville_isabella_maria_klaus
#  > Enter the name of the new simulation:      test-run
#  > Enter option:  run 1000
```
(Forkable base sims: `base_the_ville_isabella_maria_klaus` (3 agents) or
`base_the_ville_n25` (25 agents).)

### 7. Open the browser
- **Watch:** http://localhost:8000/simulator_home
- **Play:** http://localhost:8000/simulator_play?name=Alex

The agents start moving as the run proceeds.

---

## B. Docker / Synology / Portainer

See **`DOCKER.md`** for the full walkthrough. In brief:

```bash
# build + run locally
export ANTHROPIC_API_KEY=sk-ant-...
docker compose up --build
# then open http://localhost:8000/simulator_play?name=Alex
# and start the backend inside the container:
docker exec -it generative-agents bash -lc \
  'cd /app/reverie/backend_server && python reverie.py'
```
On Portainer, deploy `docker-compose.yml` as a Stack, set `ANTHROPIC_API_KEY`,
and start the backend via the container Console.

---

## First-run verification checklist

- [ ] http://localhost:8000/ shows the "up and running" page.
- [ ] `reverie.py` prints the agents' ethics note and reaches `Enter option:`.
- [ ] After `run N` and opening the browser, agents move on the map.
- [ ] **Top-right status dot is green** (WebSocket live) — grey means it fell
      back to polling (still works, but the Channels path isn't active).
- [ ] In play mode, walking near an agent and sending a message yields a reply
      in the chat panel (requires an active `run`).

---

## Known caveats / things to watch (honest list)

1. **Claude prompt tuning is unverified.** The agents' prompts and the
   JSON-wrapping response parsers were written for the original
   completion-style OpenAI models. Claude (especially Haiku) may format some
   replies differently, which can trip the validators and make a call fall back
   to its safe default. The sim will still run, but if early agent behavior
   looks flat, prompt tuning in `run_gpt_prompt.py` / `gpt_structure.py` is the
   place to look. **This is the most likely thing to need iteration.**
2. **Dependency resolution is unverified.** The `django-cors-headers` /
   `django-storages` ↔ Django 2.2 version ranges weren't run through a real
   `pip`. If install fails, pin the repo's originals:
   `django-cors-headers==2.5.3`, `django-storages-redux==1.3.3`.
3. **Start fresh from a `base_*` sim.** Do not resume an old `July1_*` run — its
   embeddings are a different dimensionality than the local model.
4. **Cost.** Each step makes several Claude calls per agent; conversation and
   reflection use the stronger (Sonnet) tier. Start with the 3-agent base sim.
5. **WebSockets need Channels.** If `channels` isn't installed the dot stays
   grey and the app uses polling — functional, just not real-time.
6. **`selenium` is a dead import** kept only because `reverie.py` imports it at
   module load; nothing launches a browser.
