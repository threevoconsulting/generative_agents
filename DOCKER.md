# Running on Synology / Portainer (Docker)

This packages the simulation as a **single container**: the Django environment
(web) server runs as the main process and keeps the container alive, and the
interactive simulation backend (`reverie.py`) is launched on demand via a
console session. Both share the container filesystem, so the file-based
handshake between them works without extra wiring.

Verified suitable for **Intel (x86) Synology models such as the DS220+** with a
few GB of RAM. (ARM models are not recommended — PyTorch, pulled in by local
embeddings, has poor ARM wheel support.)

## What you need
- An **Anthropic API key** (Claude). The NAS needs outbound internet to
  `api.anthropic.com`.
- Docker / Container Manager + Portainer on the NAS.
- A Mac or PC with Docker to build the image (no registry / Docker Hub needed).

## Step 1 — Build the image (for the NAS's architecture) and export it
The image is large because of PyTorch, so build it on your Mac/PC rather than on
the DS220+. The DS220+ is **Intel/amd64**, so build for that platform — this
matters if you build on an **Apple Silicon Mac** (otherwise you'd get an arm64
image that fails on the NAS with "exec format error"). In the repo root:
```bash
docker build --platform linux/amd64 -t generative-agents:latest .
docker save  -o generative-agents.tar generative-agents:latest
```
This produces `generative-agents.tar` (a few GB). The `--platform` flag is
harmless on an Intel Mac/PC (already amd64).

> **Test it locally first (optional but recommended).** Run the same image on
> your machine before exporting: `export ANTHROPIC_API_KEY=sk-ant-...` then
> `docker compose up -d` and open <http://localhost:8000/simulator_home>. On
> Apple Silicon this runs under emulation (slower), but it verifies the image
> works *as it will on the NAS*.

## Step 2 — Import the image into Portainer
1. Copy `generative-agents.tar` to a place the NAS can reach (e.g. a shared
   folder, or just upload it through the browser).
2. In Portainer: **Images → Import**, upload `generative-agents.tar`.
   It registers as `generative-agents:latest`.

## Step 3 — Deploy the stack with Portainer
1. In Portainer: **Stacks → Add stack**.
2. Paste the contents of `docker-compose.yml` (Web editor).
3. Under **Environment variables**, set:
   - `ANTHROPIC_API_KEY` = your key
   - (optional) `DJANGO_ALLOWED_HOSTS` = `*` (already defaulted in the compose)
4. **Deploy the stack.** `pull_policy: never` makes it use the image you
   imported instead of trying to pull from a registry. (To ship an update
   later: rebuild + `docker save` on your PC, re-import in Portainer, redeploy.)

## Start a simulation
1. Open the environment server: `http://<nas-ip>:8000/` — you should see the
   "environment server is up" page.
2. Start the agent backend: in Portainer open the **generative-agents**
   container → **Console** → connect with `/bin/bash`, then:
   ```bash
   cd /app/reverie/backend_server
   python reverie.py
   #  > Enter the name of the forked simulation:  base_the_ville_isabella_maria_klaus
   #  > Enter the name of the new simulation:      my-run
   #  > Enter option:  run 1000
   ```
3. In your browser, open one of:
   - **Play mode:** `http://<nas-ip>:8000/simulator_play?name=Alex`
   - **Watch mode:** `http://<nas-ip>:8000/simulator_home`

   The agents move as the run proceeds. The top-right dot is **green** when the
   real-time WebSocket is connected, **grey** if it fell back to polling.

## Run locally with Ollama (no API key, no cost)

Instead of Claude, you can drive the agents with a **local model served by
[Ollama](https://ollama.com)** on your Mac/PC. This is the cheapest way to run
and iterate; conversation quality is lower than Claude, but on a 32GB
Apple-silicon Mac the defaults are believable at a usable speed. **The model
runs on your host; the simulation runs in the container** — so the only real
setup is wiring the two together.

### 1. Start Ollama on the host and pull the model
```bash
# Listen on all interfaces so the container can reach it (NOT just 127.0.0.1),
# then pull the model. Leave this server running.
OLLAMA_HOST=0.0.0.0:11434 ollama serve      # one terminal
ollama pull qwen2.5:14b-instruct            # another terminal
```
> The `OLLAMA_HOST` above is **Ollama's own server-bind** variable — unrelated
> to the app's `OLLAMA_HOST` (the client URL) in step 2. The names coincide.

### 2. Point the container at it
Uncomment the Ollama `environment:` block in `docker-compose.override.yml`
(it sets `LLM_PROVIDER=ollama` and `OLLAMA_HOST=http://host.docker.internal:11434`),
then bring the stack up locally:
```bash
docker compose up -d        # merges docker-compose.yml + the override
```
`ANTHROPIC_API_KEY` can be left empty in this mode. The override also adds
`extra_hosts: host.docker.internal:host-gateway` so this works on Linux hosts
too (Docker Desktop on Mac/Windows already resolves that name).

### 3. Run it
Same as ["Start a simulation"](#start-a-simulation) above — open
`http://localhost:8000/`, then in the container console run `python reverie.py`.

### Notes for the local Ollama path
- **First step is slow.** On first use the container downloads the embedding
  model (`bge-large-en-v1.5`, ~1.3GB from HuggingFace, so the container needs
  internet once), and Ollama loads the LLM into RAM. Subsequent steps are
  steady.
- **Build a native arm64 image for a faster Mac experience.** The NAS image is
  amd64 and runs *emulated* on Apple Silicon, which slows the in-container
  embeddings. For local-only use, build native: `docker build -t
  generative-agents:latest .` (drop `--platform linux/amd64`). The LLM itself
  always runs natively on the host via Ollama regardless.
- **Verify connectivity** from inside the container if generation errors out:
  `curl http://host.docker.internal:11434/api/tags` should list your model.

## Notes & troubleshooting
- **Persistence:** generated simulations live in the `ga_storage` named volume
  and survive restarts. It is seeded from the image's bundled `base_*`
  simulations on first run.
- **Always start fresh** from a `base_*` simulation. Do not resume an old
  `July1_*` run (different embedding dimensionality).
- **Provider/cost:** defaults to Claude (Haiku for most calls, Sonnet for
  conversation/reflection) + local `bge-large-en-v1.5` embeddings (no embedding
  API cost). To use OpenAI instead, set `LLM_PROVIDER=openai`,
  `EMBEDDING_BACKEND=openai`, and `OPENAI_API_KEY` in the stack env. To run
  **fully local with no API key**, see ["Run locally with Ollama"](#run-locally-with-ollama-no-api-key-no-cost) above.
- **If the image build fails on a dependency**, the likely culprit is the
  Django add-on version range in `environment/frontend_server/requirements.txt`;
  pinning `django-cors-headers==2.5.3` and `django-storages-redux==1.3.3` (the
  repo's original pins) is the documented fallback.
- **Image size:** PyTorch makes the image large (multi-GB). Switching to
  `EMBEDDING_BACKEND=openai` removes PyTorch entirely if you want a small image.
```
