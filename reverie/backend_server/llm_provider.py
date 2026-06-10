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
import json
import difflib

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
#   "claude"  -> Anthropic API (best quality, paid)
#   "openai"  -> OpenAI API (paid)
#   "ollama"  -> a local model served by Ollama (free, runs on your hardware)
LLM_PROVIDER = _cfg("LLM_PROVIDER", "claude").lower()        # claude | openai | ollama
EMBEDDING_BACKEND = _cfg("EMBEDDING_BACKEND", "local").lower()  # "local" | "openai"

# Model identifiers per tier. Override any of these via env var or utils.py.
CLAUDE_MODEL_CHEAP = _cfg("CLAUDE_MODEL_CHEAP", "claude-haiku-4-5-20251001")
CLAUDE_MODEL_STRONG = _cfg("CLAUDE_MODEL_STRONG", "claude-sonnet-4-6")
OPENAI_MODEL_CHEAP = _cfg("OPENAI_MODEL_CHEAP", "gpt-4o-mini")
OPENAI_MODEL_STRONG = _cfg("OPENAI_MODEL_STRONG", "gpt-4o")

# Ollama (local). Defaults are tuned for a 32GB Apple-silicon Mac: Qwen2.5-14B
# (the balanced sweet spot) for both tiers. Bump the "strong" tier to
# "qwen2.5:32b-instruct" if you have the RAM and want better conversations.
# OLLAMA_HOST: when the backend runs inside Docker on a Mac, the Ollama server
# lives on the *host*, so point at host.docker.internal, e.g.
#   OLLAMA_HOST=http://host.docker.internal:11434
OLLAMA_HOST = _cfg("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL_CHEAP = _cfg("OLLAMA_MODEL_CHEAP", "qwen2.5:14b-instruct")
OLLAMA_MODEL_STRONG = _cfg("OLLAMA_MODEL_STRONG", "qwen2.5:14b-instruct")
# Context window the local model is loaded with. Bigger = more retrieved memory
# fits in each prompt (better grounding), at the cost of RAM/speed.
OLLAMA_NUM_CTX = int(_cfg("OLLAMA_NUM_CTX", "8192"))
# Repetition penalty curbs the looping/echoing that small local models fall
# into, which noticeably improves conversation quality.
OLLAMA_REPEAT_PENALTY = float(_cfg("OLLAMA_REPEAT_PENALTY", "1.1"))

# Embedding models. The local backend uses sentence-transformers (runs on the
# server, no API cost, no rate limits). The default is bge-large-en-v1.5, which
# gives substantially better memory retrieval than the older all-MiniLM-L6-v2
# (set LOCAL_EMBED_MODEL=all-MiniLM-L6-v2 to revert to the smaller/faster one).
# NOTE: switching embedding model changes the vector dimensionality, so it is
# only safe to resume a simulation with the same model it was created under.
# Base simulations ship with empty embedding stores, so starting fresh is safe.
LOCAL_EMBED_MODEL = _cfg("LOCAL_EMBED_MODEL", "BAAI/bge-large-en-v1.5")
OPENAI_EMBED_MODEL = _cfg("OPENAI_EMBED_MODEL", "text-embedding-3-small")

# Default cap on generated tokens for chat-style calls that don't specify one.
DEFAULT_MAX_TOKENS = int(_cfg("LLM_DEFAULT_MAX_TOKENS", "1024"))

# Language the model should write in. Some strong local models (notably Qwen,
# which is bilingual) drift into Chinese on free-form generations; pinning the
# output language keeps agent speech and descriptions readable. Set to any
# language name, e.g. RESPONSE_LANGUAGE="Spanish".
RESPONSE_LANGUAGE = _cfg("RESPONSE_LANGUAGE", "English")

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
    f"return just that. Always write your entire output in {RESPONSE_LANGUAGE}, "
    "regardless of the language of the prompt or any examples in it.")

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
  if LLM_PROVIDER == "ollama":
    return OLLAMA_MODEL_STRONG if strong else OLLAMA_MODEL_CHEAP
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
                  stop=None, json_mode=False):
  """
  Generate text from the configured provider.

  ARGS:
    prompt: the user prompt string.
    tier: "cheap" (high-frequency calls) or "strong" (conversation/reflection).
    max_tokens: cap on output tokens; defaults to DEFAULT_MAX_TOKENS.
    temperature: sampling temperature, clamped to [0, 1].
    stop: optional stop string or list of strings.
    json_mode: if True, ask the provider to constrain output to valid JSON.
      Honoured by the Ollama provider (via the native `format: json` grammar),
      which is the most effective way to stop small local models from breaking
      the structured formats this codebase parses. Ignored by providers that
      don't expose it.
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
      elif LLM_PROVIDER == "ollama":
        return _ollama_generate(model, prompt, max_tokens, temperature, stop,
                                json_mode)
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
# Constrained choice ("pick one of these options")                            #
# --------------------------------------------------------------------------- #
def _snap_to_choice(raw, choices):
  """Map free-form model text to exactly one of <choices>: exact match first,
  then substring either way, then closest fuzzy match. Guarantees a return value
  that is one of <choices> (defaults to the first)."""
  raw = (raw or "").strip().strip("{}").strip().strip('"').strip()
  low = raw.lower()
  for c in choices:
    if low == c.lower():
      return c
  for c in choices:
    if c.lower() in low or (low and low in c.lower()):
      return c
  match = difflib.get_close_matches(raw, choices, n=1, cutoff=0.0)
  return match[0] if match else choices[0]


def generate_choice(prompt, choices, tier="cheap", temperature=0.0):
  """
  Return exactly one value from <choices>.

  This is how we keep the agents on the real map. With Ollama we constrain the
  decode to the exact set (a JSON-schema enum -> grammar-constrained sampling),
  so the model physically cannot answer with anything outside <choices>. For
  every provider we then snap the result to the nearest valid choice, so the
  return value is ALWAYS one of <choices> even if the model misbehaves.
  """
  choices = [c.strip() for c in choices if isinstance(c, str) and c.strip()]
  if not choices:
    return None
  if len(choices) == 1:
    return choices[0]

  raw = ""
  for attempt in range(_MAX_RETRIES):
    try:
      if LLM_PROVIDER == "ollama":
        raw = _ollama_choice(_model_for_tier(tier), prompt, choices, temperature)
      else:
        raw = generate_text(prompt, tier=tier, temperature=temperature,
                            max_tokens=30)
      break
    except Exception:
      time.sleep(2 ** attempt)
  return _snap_to_choice(raw, choices)


def _ollama_choice(model, prompt, choices, temperature):
  """Ask Ollama for one of <choices>, constraining the output with a JSON-schema
  enum so the answer is guaranteed to be a member of the set."""
  import requests
  schema = {
      "type": "object",
      "properties": {"answer": {"type": "string", "enum": choices}},
      "required": ["answer"],
  }
  user = (prompt + "\n\nReturn JSON of the form {\"answer\": \"<option>\"} where "
          "<option> is exactly one of: " + ", ".join(choices) + ".")
  payload = {
      "model": model,
      "stream": False,
      "format": schema,
      "options": {"temperature": temperature, "num_ctx": OLLAMA_NUM_CTX,
                  "repeat_penalty": OLLAMA_REPEAT_PENALTY},
      "messages": [{"role": "system", "content": SYSTEM_INSTRUCTION},
                   {"role": "user", "content": user}],
  }
  resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=300)
  resp.raise_for_status()
  content = resp.json().get("message", {}).get("content", "") or ""
  try:
    return json.loads(content).get("answer", content)
  except Exception:
    return content


def _ollama_generate(model, prompt, max_tokens, temperature, stop, json_mode):
  """
  Generate text from a local model served by Ollama via its native /api/chat
  endpoint. We use the native API (rather than the OpenAI-compat shim) so we can
  pass `format: "json"` for grammar-constrained output and `repeat_penalty` to
  curb the looping that small local models are prone to.
  """
  import requests
  options = {
      "temperature": temperature,
      "num_predict": max_tokens,
      "num_ctx": OLLAMA_NUM_CTX,
      "repeat_penalty": OLLAMA_REPEAT_PENALTY,
  }
  if stop:
    options["stop"] = stop
  payload = {
      "model": model,
      "stream": False,
      "options": options,
      "messages": [{"role": "system", "content": SYSTEM_INSTRUCTION},
                   {"role": "user", "content": prompt}],
  }
  if json_mode:
    payload["format"] = "json"
  resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=300)
  resp.raise_for_status()
  return resp.json().get("message", {}).get("content", "") or ""


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
