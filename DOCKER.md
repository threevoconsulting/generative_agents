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
- A PC with Docker to build the image (no registry / Docker Hub needed).

## Step 1 — Build the image on your PC and export it to a file
The image is large because of PyTorch, so build it on a real machine rather than
on the DS220+. In the repo root:
```bash
docker build -t generative-agents:latest .
docker save  -o generative-agents.tar generative-agents:latest
```
This produces `generative-agents.tar` (a few GB).

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

## Notes & troubleshooting
- **Persistence:** generated simulations live in the `ga_storage` named volume
  and survive restarts. It is seeded from the image's bundled `base_*`
  simulations on first run.
- **Always start fresh** from a `base_*` simulation. Do not resume an old
  `July1_*` run (different embedding dimensionality).
- **Provider/cost:** defaults to Claude (Haiku for most calls, Sonnet for
  conversation/reflection) + local embeddings (no embedding API cost). To use
  OpenAI instead, set `LLM_PROVIDER=openai`, `EMBEDDING_BACKEND=openai`, and
  `OPENAI_API_KEY` in the stack env.
- **If the image build fails on a dependency**, the likely culprit is the
  Django add-on version range in `environment/frontend_server/requirements.txt`;
  pinning `django-cors-headers==2.5.3` and `django-storages-redux==1.3.3` (the
  repo's original pins) is the documented fallback.
- **Image size:** PyTorch makes the image large (multi-GB). Switching to
  `EMBEDDING_BACKEND=openai` removes PyTorch entirely if you want a small image.
```
