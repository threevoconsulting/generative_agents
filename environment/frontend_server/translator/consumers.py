"""
File: consumers.py
Description: WebSocket consumer that replaces the per-frame HTTP polling between
the Phaser frontend and the simulation backend.

The reverie backend still communicates through the shared filesystem (writing
movement/<step>.json and player_chat_response.json), so this consumer bridges
the browser WebSocket to those files: it writes what the browser sends and
*pushes* results to the browser the moment the backend produces them, instead of
the browser polling every frame.

Long waits (waiting on a movement file while the backend runs its LLM calls, or
waiting on an agent's chat reply) run as background tasks so they never block the
consumer from handling other messages -- e.g. the player can keep chatting while
a movement computation is still pending.

Only loaded when `channels` is installed. If it is not, the frontend falls back
to the legacy XHR endpoints automatically.
"""
import os
import json
import asyncio

from channels.generic.websocket import AsyncWebsocketConsumer


def _exists(path):
  return os.path.isfile(path)


def _write_json(path, obj):
  with open(path, "w") as outfile:
    outfile.write(json.dumps(obj, indent=2))


class SimConsumer(AsyncWebsocketConsumer):

  async def connect(self):
    self._tasks = set()
    await self.accept()

  async def disconnect(self, code):
    for task in list(getattr(self, "_tasks", [])):
      task.cancel()

  def _spawn(self, coro):
    task = asyncio.ensure_future(coro)
    self._tasks.add(task)
    task.add_done_callback(lambda t: self._tasks.discard(t))

  async def receive(self, text_data=None, bytes_data=None):
    try:
      data = json.loads(text_data)
    except (TypeError, ValueError):
      return
    action = data.get("action")

    if action == "process":
      # Browser -> backend: persist the current world state for this step.
      sim_code = data["sim_code"]
      step = data["step"]
      path = f"storage/{sim_code}/environment/{step}.json"
      _write_json(path, data["environment"])
      await self.send(json.dumps({"action": "process_ok", "step": step}))

    elif action == "await_movement":
      # Backend -> browser: push the movement file as soon as it appears.
      self._spawn(self._watch_movement(data["sim_code"], data["step"]))

    elif action == "player_chat":
      # Player -> agent: drop the request and push the reply when it lands.
      self._spawn(self._handle_player_chat(data))

  async def _watch_movement(self, sim_code, step):
    path = f"storage/{sim_code}/movement/{step}.json"
    while True:
      if _exists(path):
        try:
          with open(path) as json_file:
            movement = json.load(json_file)
        except (ValueError, OSError):
          await asyncio.sleep(0.1)
          continue
        movement["action"] = "movement"
        movement["<step>"] = step
        await self.send(json.dumps(movement))
        return
      await asyncio.sleep(0.1)

  async def _handle_player_chat(self, data):
    sim_code = data["sim_code"]
    payload = {"target": data.get("target", ""),
               "player_name": data.get("player_name", "Player"),
               "utterance": data.get("utterance", ""),
               "history": data.get("history", []),
               "end": data.get("end", False)}
    _write_json(f"storage/{sim_code}/player_chat.json", payload)

    # An "end" request expects no reply -- the backend just records the convo.
    if payload["end"] and not payload["utterance"]:
      return

    resp_path = f"storage/{sim_code}/player_chat_response.json"
    for _ in range(600):  # ~2 min ceiling, then give up silently
      if _exists(resp_path):
        try:
          with open(resp_path) as json_file:
            resp = json.load(json_file)
          os.remove(resp_path)
        except (ValueError, OSError):
          await asyncio.sleep(0.2)
          continue
        resp["action"] = "player_chat_response"
        await self.send(json.dumps(resp))
        return
      await asyncio.sleep(0.2)
