# Local Setup Guide — Running on a Mac with Ollama (no API key, no cost)

This is a detailed, start-to-finish guide for running the generative-agents
simulation **locally on a Mac**, using a local LLM served by
[Ollama](https://ollama.com) instead of a paid API. It runs the two servers
**natively** (no Docker) — the simplest and fastest local setup.

> Prefer Claude or OpenAI, or deploying to a NAS? See the main
> [README](README.md) and [DOCKER.md](DOCKER.md). This guide is specifically
> the free, fully-local path.

---

## 0. How it fits together (30-second mental model)

The simulation is **two servers plus a model**:

| Piece | What it is | Where it runs |
| --- | --- | --- |
| **Environment server** | Django web app — draws the map, serves the browser UI | `localhost:8000` |
| **Simulation backend** (`reverie.py`) | The agent "brains" — perception, planning, reflection, conversation | your terminal |
| **Ollama** | Serves the local LLM the backend calls for every decision | `localhost:11434` |

The two servers talk to each other through the local filesystem, and the
backend talks to Ollama over HTTP. Embeddings (for agent memory) run **inside
the backend process** via `sentence-transformers` — no extra server needed.

---

## 1. Prerequisites

- **macOS** on Apple silicon (M-series) or Intel.
- **~16GB RAM minimum, 32GB recommended.** The default model (Qwen2.5-14B)
  needs roughly 10GB free while running; 32GB lets you step up to the 32B model.
- **Python 3.9.** This is not optional: the environment server uses Django 2.2,
  which **does not run on Python 3.10+**. The project was tested on 3.9.12.
- **~15GB free disk** (model weights + Python deps + embedding model).

Check your Python:
```bash
python3 --version          # must report 3.9.x
```
If you don't have 3.9, install it with [pyenv](https://github.com/pyenv/pyenv):
```bash
brew install pyenv
pyenv install 3.9.18
pyenv local 3.9.18         # pins 3.9 for this repo directory
```

---

## 2. Install Ollama and pull the model

1. Install Ollama from <https://ollama.com> (the macOS app), or via Homebrew:
   ```bash
   brew install ollama
   ```
2. Start the Ollama server. The desktop app does this automatically; from the
   CLI, run this in its own terminal and leave it running:
   ```bash
   ollama serve
   ```
3. Pull the default model (in another terminal):
   ```bash
   ollama pull qwen2.5:14b-instruct
   ```
4. Verify it's there:
   ```bash
   curl http://localhost:11434/api/tags
   # should list "qwen2.5:14b-instruct"
   ```

> Running natively on the Mac, Ollama on `localhost` is all you need — none of
> the `0.0.0.0` / `host.docker.internal` wiring in DOCKER.md applies (that's
> only for crossing a container boundary).

---

## 3. Get the code and create a virtual environment

```bash
git clone <your-fork-url> generative_agents
cd generative_agents

python3 -m venv venv
source venv/bin/activate        # run this in every new terminal you use
```

---

## 4. Install Python dependencies

There are **two** requirements files — one per server. Install both into the
same venv:

```bash
pip install --upgrade pip
pip install -r requirements.txt                              # backend (agents + embeddings)
pip install -r environment/frontend_server/requirements.txt  # Django web server
```

This installs `sentence-transformers` (which pulls in CPU PyTorch) for local
embeddings, plus Django 2.2 and Channels for the web server.

---

## 5. Create `utils.py`

The backend needs a `utils.py` config file. It is gitignored, but a ready-made
template ships in the repo — copy it:

```bash
cp reverie/backend_server/utils.docker.py reverie/backend_server/utils.py
```

The template's relative paths are correct for running from
`reverie/backend_server`, and it reads no API key — perfect for the Ollama path.

---

## 6. Run it

You need **two terminals**, both with the venv activated (`source venv/bin/activate`).

### Terminal A — environment (web) server
```bash
cd environment/frontend_server
python manage.py runserver
```
Open <http://localhost:8000/>. You should see **"Your environment server is up
and running."** Leave this terminal running.

### Terminal B — simulation backend (pointed at Ollama)
```bash
cd reverie/backend_server
export LLM_PROVIDER=ollama       # <-- the one switch that makes it use Ollama
python reverie.py
```
At the prompts:
```
Enter the name of the forked simulation:   base_the_ville_isabella_maria_klaus
Enter the name of the new simulation:       test-run
Enter option:                               run 100
```
- The **forked** name is the starting point — `base_the_ville_isabella_maria_klaus`
  is the bundled 3-agent town (Isabella, Maria, Klaus).
- The **new** name is whatever you want to call this run.
- `run 100` simulates 100 steps (1 step = 10 in-game seconds).

### Browser — watch or play
- **Watch:** <http://localhost:8000/simulator_home>
- **Play (talk to them):** <http://localhost:8000/simulator_play?name=Alex> —
  move with arrow keys, walk up to a resident, and a chat panel appears. The
  agents perceive you and remember your conversations.

> Agents only reply while a run is **actively** in progress, so for play mode
> start a long run (e.g. `run 1000`) and interact as it proceeds.

---

## 7. What to expect on the first run

- **One-time embedding-model download.** The first time an agent memory is
  embedded, `sentence-transformers` downloads `bge-large-en-v1.5` (~1.3GB) from
  HuggingFace. Needs internet once, then it's cached in `~/.cache`.
- **The first step is slow.** Ollama loads the 14B model into RAM and the first
  embeddings compute. Subsequent steps are much faster.
- **It's chatty in the logs.** That's normal — each step makes many model calls.

---

## 8. Stopping, saving, resuming

At the `Enter option:` prompt:
- `run <n>` — simulate `n` more steps.
- `fin` — **save and exit.** Resume later by giving this run's name as the
  *forked* simulation.
- `exit` — quit **without** saving.

> **Always fork from a `base_*` simulation for a brand-new run.** Do not fork an
> old simulation that was created under a different embedding model — vector
> dimensionality won't match. Runs you create now (with `bge-large-en-v1.5`) are
> consistent with each other and safe to resume.

---

## 9. Tuning quality vs. speed

All of these are environment variables you set in **Terminal B** before
`python reverie.py` (they override the defaults in
`reverie/backend_server/llm_provider.py`):

| Variable | Default | Effect |
| --- | --- | --- |
| `OLLAMA_MODEL_STRONG` | `qwen2.5:14b-instruct` | Model for **conversation & reflection**. Set to `qwen2.5:32b-instruct` (pull it first) for noticeably better dialogue if you have 32GB. Cheap/frequent calls stay on 14B for speed. |
| `OLLAMA_MODEL_CHEAP` | `qwen2.5:14b-instruct` | Model for the many high-frequency planning/perception calls. Drop to `qwen2.5:7b-instruct` to trade some quality for speed. |
| `OLLAMA_NUM_CTX` | `8192` | Context window. Larger fits more retrieved memory per prompt (better grounding) but uses more RAM and is slower. |
| `OLLAMA_REPEAT_PENALTY` | `1.1` | Curbs the repetitive looping small local models fall into. Raise toward `1.2` if dialogue gets repetitive. |
| `LOCAL_EMBED_MODEL` | `BAAI/bge-large-en-v1.5` | Memory-retrieval embedding model. Set to `all-MiniLM-L6-v2` for a smaller/faster (lower-quality) model. **Changing this changes vector size — start a fresh run if you switch.** |

Example — better conversations on a 32GB Mac:
```bash
ollama pull qwen2.5:32b-instruct
export LLM_PROVIDER=ollama
export OLLAMA_MODEL_STRONG=qwen2.5:32b-instruct
python reverie.py
```

---

## 10. Troubleshooting

**`Connection refused` / generation errors to port 11434**
Ollama isn't running or isn't reachable. Check `ollama serve` is up and
`curl http://localhost:11434/api/tags` responds.

**`model "qwen2.5:14b-instruct" not found`**
You haven't pulled it: `ollama pull qwen2.5:14b-instruct`. Names must match
exactly (including the `:14b-instruct` tag).

**Agents act "brain-dead" / give flat, generic responses**
Usually the model is failing the structured formats the simulation parses. The
provider already sends structured calls with a JSON grammar constraint and a
repetition penalty; if it persists, try a larger model for the strong tier
(`OLLAMA_MODEL_STRONG=qwen2.5:32b-instruct`).

**`ImportError` / Django errors on `manage.py runserver`**
You're almost certainly on Python 3.10+. Django 2.2 requires **Python 3.9** —
recreate the venv with 3.9 (see §1).

**`ModuleNotFoundError: utils`**
You skipped §5 — `cp reverie/backend_server/utils.docker.py
reverie/backend_server/utils.py`.

**`Port 8000 already in use`**
Another process (or a previous run) holds it. Stop it, or run the web server on
another port: `python manage.py runserver 8001` (then use `:8001` in the URLs).

**First step hangs for a long time**
Expected once — model load + embedding-model download. Watch Terminal B; it
proceeds after the model is resident in RAM.

**It's still calling Claude / asking for an API key**
Make sure `export LLM_PROVIDER=ollama` was run in the **same** terminal as
`python reverie.py`. The env var is per-shell.
