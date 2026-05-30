"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: gpt_structure.py
Description: Wrapper functions for calling LLM APIs.

This module is now provider-agnostic: every call delegates to llm_provider,
which can be pointed at Claude (default) or OpenAI for text, and at a local
sentence-transformers model (default) or OpenAI for embeddings. See
llm_provider.py for configuration. The public function names and signatures
below are unchanged so the rest of the codebase keeps working untouched.

Tiering: low-judgment, high-frequency calls use the "cheap" tier; the GPT-4
entry points map to the "strong" tier.
"""
import json
import re
import time

from llm_provider import generate_text, embed, ERROR_SENTINEL


def temp_sleep(seconds=0.1):
  time.sleep(seconds)


def ChatGPT_single_request(prompt):
  temp_sleep()
  return generate_text(prompt, tier="cheap")


# ============================================================================
# #####################[SECTION 1: CHAT STRUCTURE] ##########################
# ============================================================================

def GPT4_request(prompt):
  """
  Make a request to the configured "strong" model and return the response.
  ARGS:
    prompt: a str prompt
  RETURNS:
    a str of the model's response.
  """
  temp_sleep()
  try:
    return generate_text(prompt, tier="strong")
  except:
    print("LLM ERROR")
    return ERROR_SENTINEL


def ChatGPT_request(prompt):
  """
  Make a request to the configured "cheap" model and return the response.
  ARGS:
    prompt: a str prompt
  RETURNS:
    a str of the model's response.
  """
  try:
    return generate_text(prompt, tier="cheap")
  except:
    print("LLM ERROR")
    return ERROR_SENTINEL


def _extract_json_output(raw):
  """Best-effort pull of the 'output' value from a model reply that is supposed
  to be JSON like {"output": "..."}. Tolerates ``` code fences, surrounding
  prose, and single quotes; falls back to the raw de-fenced text when there is
  no parseable JSON (these prompts often make the model just return the bare
  phrase). Returns a string, or None if nothing usable came back."""
  if not raw or raw == ERROR_SENTINEL:
    return None
  s = raw.strip()
  if s.startswith("```"):                         # strip ``` / ```json fences
    s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
    s = re.sub(r"\s*```$", "", s).strip()
  for m in re.finditer(r"\{.*?\}", s, re.DOTALL):  # find a JSON obj w/ "output"
    chunk = m.group(0)
    for candidate in (chunk, chunk.replace("'", '"')):
      try:
        obj = json.loads(candidate)
        if isinstance(obj, dict) and "output" in obj:
          return str(obj["output"])
      except Exception:
        pass
  s = s.strip().strip('"').strip("'").strip()      # fall back to bare text
  return s or None


def _json_safe_generate(prompt, example_output, special_instruction, tier,
                        repeat, fail_safe_response, func_validate, func_clean_up,
                        verbose):
  """Shared core for the JSON-wrapped prompt helpers. Unlike the original, this
  NEVER returns False/None: the ~16 callers do `if output != False: return
  output` with no real fallback, so returning False made them return None and
  crash downstream (e.g. 'NoneType' object is not subscriptable). On repeated
  failure we degrade to <fail_safe_response>."""
  wrapped = ('"""\n' + prompt + '\n"""\n'
             + f"Output the response to the prompt above in json. "
             + f"{special_instruction}\n"
             + "Example output json:\n"
             + '{"output": "' + str(example_output) + '"}')
  if verbose:
    print("LLM PROMPT")
    print(wrapped)

  for i in range(repeat):
    # temperature=0 -> deterministic and far more reliably parseable than the
    # previous default (0.7), which made these structured calls flaky.
    extracted = _extract_json_output(generate_text(wrapped, tier=tier,
                                                   temperature=0))
    if extracted is None:
      continue
    try:
      if func_validate(extracted, prompt=wrapped):
        return func_clean_up(extracted, prompt=wrapped)
    except Exception:
      pass
    if verbose:
      print("---- repeat count:", i, extracted)

  return fail_safe_response


def GPT4_safe_generate_response(prompt,
                                   example_output,
                                   special_instruction,
                                   repeat=3,
                                   fail_safe_response="error",
                                   func_validate=None,
                                   func_clean_up=None,
                                   verbose=False):
  return _json_safe_generate(prompt, example_output, special_instruction,
                             "strong", repeat, fail_safe_response,
                             func_validate, func_clean_up, verbose)


def ChatGPT_safe_generate_response(prompt,
                                   example_output,
                                   special_instruction,
                                   repeat=3,
                                   fail_safe_response="error",
                                   func_validate=None,
                                   func_clean_up=None,
                                   verbose=False):
  return _json_safe_generate(prompt, example_output, special_instruction,
                             "cheap", repeat, fail_safe_response,
                             func_validate, func_clean_up, verbose)


def ChatGPT_safe_generate_response_OLD(prompt,
                                   repeat=3,
                                   fail_safe_response="error",
                                   func_validate=None,
                                   func_clean_up=None,
                                   verbose=False):
  if verbose:
    print("LLM PROMPT")
    print(prompt)

  for i in range(repeat):
    try:
      curr_gpt_response = ChatGPT_request(prompt).strip()
      if func_validate(curr_gpt_response, prompt=prompt):
        return func_clean_up(curr_gpt_response, prompt=prompt)
      if verbose:
        print(f"---- repeat count: {i}")
        print(curr_gpt_response)
        print("~~~~")

    except:
      pass
  print("FAIL SAFE TRIGGERED")
  return fail_safe_response


# ============================================================================
# ###################[SECTION 2: COMPLETION-STYLE STRUCTURE] #################
# ============================================================================

def GPT_request(prompt, gpt_parameter):
  """
  Completion-style entry point retained for backwards compatibility. The
  legacy `gpt_parameter` dict (engine, max_tokens, temperature, stop, ...) is
  honoured where it maps cleanly onto the provider; the now-defunct `engine`
  field (e.g. "text-davinci-003") is ignored in favour of the configured
  "cheap" tier model.
  ARGS:
    prompt: a str prompt
    gpt_parameter: a python dictionary of generation parameters.
  RETURNS:
    a str of the model's response.
  """
  temp_sleep()
  try:
    return generate_text(
        prompt,
        tier="cheap",
        max_tokens=gpt_parameter.get("max_tokens"),
        temperature=gpt_parameter.get("temperature", 0.7),
        stop=gpt_parameter.get("stop"))
  except:
    print("TOKEN LIMIT EXCEEDED")
    return ERROR_SENTINEL


def generate_prompt(curr_input, prompt_lib_file):
  """
  Takes in the current input and the path to a prompt file. The prompt file
  contains the raw str prompt with the substr !<INPUT>! which this function
  replaces with the actual curr_input to produce the final prompt.
  ARGS:
    curr_input: the input we want to feed in (IF THERE ARE MORE THAN ONE
                INPUT, THIS CAN BE A LIST.)
    prompt_lib_file: the path to the prompt file.
  RETURNS:
    a str prompt.
  """
  if type(curr_input) == type("string"):
    curr_input = [curr_input]
  curr_input = [str(i) for i in curr_input]

  f = open(prompt_lib_file, "r")
  prompt = f.read()
  f.close()
  for count, i in enumerate(curr_input):
    prompt = prompt.replace(f"!<INPUT {count}>!", i)
  if "<commentblockmarker>###</commentblockmarker>" in prompt:
    prompt = prompt.split("<commentblockmarker>###</commentblockmarker>")[1]
  return prompt.strip()


def safe_generate_response(prompt,
                           gpt_parameter,
                           repeat=5,
                           fail_safe_response="error",
                           func_validate=None,
                           func_clean_up=None,
                           verbose=False):
  if verbose:
    print(prompt)

  for i in range(repeat):
    curr_gpt_response = GPT_request(prompt, gpt_parameter)
    if func_validate(curr_gpt_response, prompt=prompt):
      return func_clean_up(curr_gpt_response, prompt=prompt)
    if verbose:
      print("---- repeat count: ", i, curr_gpt_response)
      print(curr_gpt_response)
      print("~~~~")
  return fail_safe_response


def get_embedding(text, model=None):
  """
  Return an embedding vector for <text> using the configured embedding
  backend (local sentence-transformers by default). The <model> argument is
  accepted for backwards compatibility but ignored; configure the embedding
  model via llm_provider instead.
  """
  return embed(text)


if __name__ == '__main__':
  gpt_parameter = {"engine": "text-davinci-003", "max_tokens": 50,
                   "temperature": 0, "top_p": 1, "stream": False,
                   "frequency_penalty": 0, "presence_penalty": 0,
                   "stop": ['"']}
  curr_input = ["driving to a friend's house"]
  prompt_lib_file = "prompt_template/test_prompt_July5.txt"
  prompt = generate_prompt(curr_input, prompt_lib_file)

  def __func_validate(gpt_response):
    if len(gpt_response.strip()) <= 1:
      return False
    if len(gpt_response.strip().split(" ")) > 1:
      return False
    return True
  def __func_clean_up(gpt_response):
    cleaned_response = gpt_response.strip()
    return cleaned_response

  output = safe_generate_response(prompt,
                                 gpt_parameter,
                                 5,
                                 "rest",
                                 __func_validate,
                                 __func_clean_up,
                                 True)

  print(output)
