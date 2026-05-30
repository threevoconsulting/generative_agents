# Single-image deployment of the Generative Agents simulation + environment
# server. The environment (web) server runs as the container's main process;
# the interactive simulation backend (reverie.py) is launched on demand via an
# exec/console session (see DOCKER.md). Both share the container filesystem, so
# the file-based handshake between them works with no extra wiring.

FROM python:3.9

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install runtime dependencies first for better layer caching. These are the
# pruned backend + environment-server requirements (analysis-only libs removed).
COPY requirements.txt ./requirements.txt
COPY environment/frontend_server/requirements.txt ./frontend-requirements.txt
RUN pip install -r requirements.txt -r frontend-requirements.txt

# Copy the application code.
COPY . .

# Provide the backend config (utils.py is gitignored; ship a docker template).
RUN cp reverie/backend_server/utils.docker.py reverie/backend_server/utils.py

# Pre-download the local embedding model so the first run is fast and offline.
RUN python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('all-MiniLM-L6-v2')"

# Apply DB migrations for the environment server (idempotent; sqlite ships in repo).
WORKDIR /app/environment/frontend_server
RUN python manage.py migrate --noinput || true

EXPOSE 8000

# The environment/web server keeps the container alive. Run the simulation
# backend separately: `docker exec -it <container> bash` then
# `cd /app/reverie/backend_server && python reverie.py`.
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
