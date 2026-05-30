"""
File: llm_provider.py
Description: Provider-agnostic LLM + embedding layer for the generative agents
backend.

All text generation and embedding requests funnel through this module so the
rest of the codebase (gpt_structure.py and, transitively, run_gpt_prompt.py and
the cognitive modules) never needs to know which vendor is being used.

Two things are configurable independently:

  * The TEXT provider          -> "claude" (default) or "openai"
  * The EMBEDDING backend       -> "local" (default) or "openai"

Configuration is resolved with the following precedence (first hit wins):

  1. An environment variable (e.g. LLM_PROVIDER, ANTHROPIC_API_KEY).
  2. A matching lowercase attribute in utils.py (e.g. anthropic_api_key).
  3. The built-in default below.

This means the legacy utils.py still works, and anything can be overridden from
the shell without editing code.

Tiering: the codebase makes ~30-50 model calls per agent per step. The vast
majority are cheap classification/extraction calls; only conversation and
reflection benefit from a stronger model. Callers request a tier ("cheap" or
"strong") and this module maps it to a concrete model per provider.
"""
import os
import time

# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #
try:
  import utils as _utils
except Exception:
  _utils = None


def _cfg(name, default):
  """Resolve a config value: env var > utils.py attribute > default."""
  if name in os.environ:
    return os.environ[name]
  if _utils is not None and hasattr(_utils, name.lower()):
    return getattr(_utils, name.lower())
  return default


# Which vendor handles text generation / embeddings.
LLM_PROVIDER = _cfg("LLM_PROVIDER", "claude").lower()        # "claude" | "openai"
EMBEDDING_BACKEND = _cfg("EMBEDDING_BACKEND", "local").lower()  # "local" | "openai"

# Model identifiers per tier. Override any of these via env var or utils.py.
CLAUDE_MODEL_CHEAP = _cfg("CLAUDE_MODEL_CHEAP", "claude-haiku-4-5-20251001")
CLAUDE_MODEL_STRONG = _cfg("CLAUDE_MODEL_STRONG", "claude-sonnet-4-6")
OPENAI_MODEL_CHEAP = _cfg("OPENAI_MODEL_CHEAP", "gpt-4o-mini")
OPENAI_MODEL_STRONG = _cfg("OPENAI_MODEL_STRONG", "gpt-4o")

# Embedding models. The local backend uses sentence-transformers (runs on the
# server, no API cost, no rate limits). NOTE: switching embedding backends
# changes the vector dimensionality, so it is only safe to resume a simulation
# with the same backend it was created under. Base simulations ship with empty
# embedding stores, so starting fresh is always safe.
LOCAL_EMBED_MODEL = _cfg("LOCAL_EMBED_MODEL", "all-MiniLM-L6-v2")
OPENAI_EMBED_MODEL = _cfg("OPENAI_EMBED_MODEL", "text-embedding-3-small")

# Default cap on generated tokens for chat-style calls that don't specify one.
DEFAULT_MAX_TOKENS = int(_cfg("LLM_DEFAULT_MAX_TOKENS", "1024"))

# A short system instruction that nudges chat models to behave like the
# completion-style endpoints the original prompts were written for (i.e. emit
# exactly what is asked with no chatty preamble). Helps the existing validators
# pass on the first try and avoids wasted retries.
SYSTEM_INSTRUCTION = (
    "You are a text-completion engine embedded in a larger program, standing in "
    "for an OpenAI completion model. The user message is a prompt that usually "
    "ends mid-sentence or mid-list; continue it directly. Output ONLY the "
    "continuation text the program expects -- no preamble, no explanation, no "
    "restating of the prompt, no markdown formatting, no headers or titles, and "
    "no surrounding quotes or code fences. Match the exact format shown by any "
    "examples in the prompt. If the prompt asks for a single value or line, "
    "return just that.")

# Sentinel returned on hard failures. The existing retry/validate logic treats
# any non-conforming string as a failed attempt, so this preserves behaviour.
ERROR_SENTINEL = "LLM PROVIDER ERROR"

# Number of network retries (with exponential backoff) on transient API errors.
_MAX_RETRIES = 3


# --------------------------------------------------------------------------- #
# Lazy client / model singletons                                              #
# --------------------------------------------------------------------------- #
_anthropic_client = None
_openai_client = None
_local_embedder = None
_embedding_cache = {}


def _get_anthropic():
  global _anthropic_client
  if _anthropic_client is None:
    import anthropic
    key = _cfg("ANTHROPIC_API_KEY", None)
    _anthropic_client = anthropic.Anthropic(api_key=key) if key else \
                        anthropic.Anthropic()
  return _anthropic_client


def _get_openai():
  global _openai_client
  if _openai_client is None:
    from openai import OpenAI
    key = _cfg("OPENAI_API_KEY", None) or _cfg("openai_api_key", None)
    _openai_client = OpenAI(api_key=key) if key else OpenAI()
  return _openai_client


def _get_local_embedder():
  global _local_embedder
  if _local_embedder is None:
    from sentence_transformers import SentenceTransformer
    _local_embedder = SentenceTransformer(LOCAL_EMBED_MODEL)
  return _local_embedder


# --------------------------------------------------------------------------- #
# Text generation                                                             #
# --------------------------------------------------------------------------- #
def _model_for_tier(tier):
  strong = (tier == "strong")
  if LLM_PROVIDER == "claude":
    return CLAUDE_MODEL_STRONG if strong else CLAUDE_MODEL_CHEAP
  return OPENAI_MODEL_STRONG if strong else OPENAI_MODEL_CHEAP


def _clean_stop(stop):
  """Normalise a stop spec into a list of non-empty strings (or None)."""
  if not stop:
    return None
  if isinstance(stop, str):
    stop = [stop]
  stop = [s for s in stop if isinstance(s, str) and s != ""]
  return stop or None


def generate_text(prompt, tier="cheap", max_tokens=None, temperature=0.7,
                  stop=None):
  """
  Generate text from the configured provider.

  ARGS:
    prompt: the user prompt string.
    tier: "cheap" (high-frequency calls) or "strong" (conversation/reflection).
    max_tokens: cap on output tokens; defaults to DEFAULT_MAX_TOKENS.
    temperature: sampling temperature, clamped to [0, 1].
    stop: optional stop string or list of strings.
  RETURNS:
    The generated string, or ERROR_SENTINEL on repeated failure.
  """
  max_tokens = max_tokens or DEFAULT_MAX_TOKENS
  temperature = max(0.0, min(1.0, float(temperature)))
  stop = _clean_stop(stop)
  model = _model_for_tier(tier)

  last_err = None
  for attempt in range(_MAX_RETRIES):
    try:
      if LLM_PROVIDER == "claude":
        return _claude_generate(model, prompt, max_tokens, temperature, stop)
      elif LLM_PROVIDER == "openai":
        return _openai_generate(model, prompt, max_tokens, temperature, stop)
      else:
        raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER}")
    except Exception as e:  # transient API/network error -> backoff and retry
      last_err = e
      time.sleep(2 ** attempt)

  print(f"[llm_provider] generate_text failed after {_MAX_RETRIES} attempts: "
        f"{last_err}")
  return ERROR_SENTINEL


def _claude_generate(model, prompt, max_tokens, temperature, stop):
  client = _get_anthropic()
  kwargs = dict(
      model=model,
      max_tokens=max_tokens,
      temperature=temperature,
      system=SYSTEM_INSTRUCTION,
      messages=[{"role": "user", "content": prompt}])
  if stop:
    # Anthropic rejects stop sequences that are only whitespace ("each stop
    # sequence must contain non-whitespace"). The legacy prompts pass stops
    # like "\n", which is valid for OpenAI but not Claude -- drop those.
    claude_stop = [s for s in stop if s.strip()]
    if claude_stop:
      kwargs["stop_sequences"] = claude_stop
  resp = client.messages.create(**kwargs)
  # Concatenate any text blocks in the response.
  return "".join(b.text for b in resp.content if getattr(b, "type", None)
                 == "text")


def _openai_generate(model, prompt, max_tokens, temperature, stop):
  client = _get_openai()
  resp = client.chat.completions.create(
      model=model,
      max_tokens=max_tokens,
      temperature=temperature,
      stop=stop,
      messages=[{"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt}])
  return resp.choices[0].message.content or ""


# --------------------------------------------------------------------------- #
# Embeddings                                                                  #
# --------------------------------------------------------------------------- #
def embed(text):
  """
  Return an embedding vector (list of floats) for <text>.

  Results are cached in-process by text, since the simulation re-embeds many
  identical descriptions (e.g. "idle", recurring action strings).
  """
  text = text.replace("\n", " ").strip()
  if not text:
    text = "this is blank"

  if text in _embedding_cache:
    return _embedding_cache[text]

  if EMBEDDING_BACKEND == "local":
    vec = _get_local_embedder().encode(text).tolist()
  elif EMBEDDING_BACKEND == "openai":
    client = _get_openai()
    vec = client.embeddings.create(
        input=[text], model=OPENAI_EMBED_MODEL).data[0].embedding
  else:
    raise ValueError(f"Unknown EMBEDDING_BACKEND: {EMBEDDING_BACKEND}")

  _embedding_cache[text] = vec
  return vec
