"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: execute.py
Description: This defines the "Act" module for generative agents. 
"""
import sys
import random
sys.path.append('../../')

from global_methods import *
from path_finder import *
from utils import *


# Keywords the LLM uses to name sleeping surfaces. The model sometimes says
# "double bed", "bunk bed", "cot", "mattress", etc. -- none of which contain
# the bare word "bed" after splitting on ":" (e.g. "...:bunk"). Matching this
# wider set keeps sleep-centering working for all of them.
BED_KEYWORDS = {"bed", "bunk", "cot", "mattress", "pillow"}


def _resolve_address_tiles(plan, maze, persona):
  """
  Return the set of tiles for the action address <plan>. If the model named a
  place that doesn't exist (e.g. a "kitchen" arena in an apartment that has
  none), degrade to a less-specific address that does exist (drop arena ->
  sector -> world). As a last resort keep the persona where they are, so a
  hallucinated location can never crash the simulation.

  When degrading, prefer tiles that carry a spawning_location marker. These are
  intentionally placed walkable positions set by the map author, so an agent
  that falls back to the sector level lands on a sensible spot rather than on a
  random tile (which could be a bathroom, doorway, or wall edge).
  """
  if plan in maze.address_tiles:
    return maze.address_tiles[plan]
  parts = plan.split(":")
  while len(parts) > 1:
    parts = parts[:-1]
    key = ":".join(parts)
    if key in maze.address_tiles:
      tiles = maze.address_tiles[key]
      # Prefer spawn-location tiles within this address when any exist.
      spawn_tiles = {t for t in tiles
                     if maze.access_tile(t).get("spawning_location")}
      return spawn_tiles if spawn_tiles else tiles
  return {tuple(persona.scratch.curr_tile)}


def execute(persona, maze, personas, plan):
  """
  Given a plan (action's string address), we execute the plan (actually 
  outputs the tile coordinate path and the next coordinate for the 
  persona). 

  INPUT:
    persona: Current <Persona> instance.  
    maze: An instance of current <Maze>.
    personas: A dictionary of all personas in the world. 
    plan: This is a string address of the action we need to execute. 
       It comes in the form of "{world}:{sector}:{arena}:{game_objects}". 
       It is important that you access this without doing negative 
       indexing (e.g., [-1]) because the latter address elements may not be 
       present in some cases. 
       e.g., "dolores double studio:double studio:bedroom 1:bed"
    
  OUTPUT: 
    execution
  """
  if "<random>" in plan and persona.scratch.planned_path == []: 
    persona.scratch.act_path_set = False

  # <act_path_set> is set to True if the path is set for the current action. 
  # It is False otherwise, and means we need to construct a new path. 
  if not persona.scratch.act_path_set: 
    # <target_tiles> is a list of tile coordinates where the persona may go 
    # to execute the current action. The goal is to pick one of them.
    target_tiles = None

    print ('aldhfoaf/????')
    print (plan)

    if "<persona>" in plan: 
      # Executing persona-persona interaction.
      target_p_tile = (personas[plan.split("<persona>")[-1].strip()]
                       .scratch.curr_tile)
      potential_path = path_finder(maze.collision_maze, 
                                   persona.scratch.curr_tile, 
                                   target_p_tile, 
                                   collision_block_id)
      if len(potential_path) <= 2: 
        target_tiles = [potential_path[0]]
      else: 
        potential_1 = path_finder(maze.collision_maze, 
                                persona.scratch.curr_tile, 
                                potential_path[int(len(potential_path)/2)], 
                                collision_block_id)
        potential_2 = path_finder(maze.collision_maze, 
                                persona.scratch.curr_tile, 
                                potential_path[int(len(potential_path)/2)+1], 
                                collision_block_id)
        if len(potential_1) <= len(potential_2): 
          target_tiles = [potential_path[int(len(potential_path)/2)]]
        else: 
          target_tiles = [potential_path[int(len(potential_path)/2+1)]]
    
    elif "<waiting>" in plan: 
      # Executing interaction where the persona has decided to wait before 
      # executing their action.
      x = int(plan.split()[1])
      y = int(plan.split()[2])
      target_tiles = [[x, y]]

    elif "<random>" in plan:
      # Executing a random location action.
      plan = ":".join(plan.split(":")[:-1])
      target_tiles = _resolve_address_tiles(plan, maze, persona)
      target_tiles = random.sample(list(target_tiles), 1)

    else:
      # This is our default execution. We simply take the persona to the
      # location where the current action is taking place.
      # Retrieve the target addresses. Again, plan is an action address in its
      # string form. <maze.address_tiles> takes this and returns candidate
      # coordinates. Resolve defensively so a hallucinated address degrades to
      # a valid one instead of crashing.
      target_tiles = _resolve_address_tiles(plan, maze, persona)

    # There are sometimes more than one tile returned from this (e.g., a tabe
    # may stretch many coordinates). So, we sample a few here. And from that 
    # random sample, we will take the closest ones. 
    if len(target_tiles) < 4: 
      target_tiles = random.sample(list(target_tiles), len(target_tiles))
    else:
      target_tiles = random.sample(list(target_tiles), 4)
    # If possible, we want personas to occupy different tiles when they are 
    # headed to the same location on the maze. It is ok if they end up on the 
    # same time, but we try to lower that probability. 
    # We take care of that overlap here.  
    persona_name_set = set(personas.keys())
    new_target_tiles = []
    for i in target_tiles: 
      curr_event_set = maze.access_tile(i)["events"]
      pass_curr_tile = False
      for j in curr_event_set: 
        if j[0] in persona_name_set: 
          pass_curr_tile = True
      if not pass_curr_tile: 
        new_target_tiles += [i]
    if len(new_target_tiles) == 0:
      new_target_tiles = target_tiles
    target_tiles = new_target_tiles

    # Sleep actions aim for the center tile of the bed cluster rather than
    # whatever edge tile the sample produced, so sleepers lie centered on
    # their bed. Doing this here -- at path-target selection -- keeps a
    # single source of truth for the persona's tile (the frontend renders
    # wherever the backend says; retargeting on the frontend made the two
    # fight). If the center is taken by someone else (a shared double bed),
    # the sampled tile is kept so partners settle on different tiles.
    act_desc = (persona.scratch.act_description or "").lower()
    last_obj = plan.split(":")[-1].lower()
    if "sleep" in act_desc and any(kw in last_obj for kw in BED_KEYWORDS):
      centered_tiles = []
      for t in target_tiles:
        pose = maze.get_game_object_pose(t)
        if pose and any(kw in pose["object"].lower() for kw in BED_KEYWORDS):
          c = (int(round(pose["anchor_tile"][0])),
               int(round(pose["anchor_tile"][1])))
          c_tile = maze.access_tile(c)
          occupied = any(j[0] in persona_name_set and j[0] != persona.name
                         for j in c_tile["events"])
          if (any(kw in (c_tile["game_object"] or "").lower()
                  for kw in BED_KEYWORDS) and not occupied):
            centered_tiles += [c]
            continue
        centered_tiles += [tuple(t)]
      target_tiles = list(dict.fromkeys(centered_tiles))

    # Now that we've identified the target tile, we find the shortest path to
    # one of the target tiles. 
    curr_tile = persona.scratch.curr_tile
    collision_maze = maze.collision_maze
    closest_target_tile = None
    path = None
    for i in target_tiles: 
      # path_finder takes a collision_mze and the curr_tile coordinate as 
      # an input, and returns a list of coordinate tuples that becomes the
      # path. 
      # e.g., [(0, 1), (1, 1), (1, 2), (1, 3), (1, 4)...]
      curr_path = path_finder(maze.collision_maze, 
                              curr_tile, 
                              i, 
                              collision_block_id)
      if not closest_target_tile: 
        closest_target_tile = i
        path = curr_path
      elif len(curr_path) < len(path): 
        closest_target_tile = i
        path = curr_path

    # Actually setting the <planned_path> and <act_path_set>. We cut the 
    # first element in the planned_path because it includes the curr_tile. 
    persona.scratch.planned_path = path[1:]
    persona.scratch.act_path_set = True

    # If BFS found no route (path_finder returned just [curr_tile], so
    # path[1:] is empty), reset act_path_set so the cognitive loop picks a
    # new action on the next step instead of freezing the agent permanently
    # in place with an empty planned_path.
    if not persona.scratch.planned_path:
      persona.scratch.act_path_set = False

  # Setting up the next immediate step. We stay at our curr_tile if there is
  # no <planned_path> left, but otherwise, we go to the next tile in the path.
  ret = persona.scratch.curr_tile
  if persona.scratch.planned_path: 
    ret = persona.scratch.planned_path[0]
    persona.scratch.planned_path = persona.scratch.planned_path[1:]

  description = f"{persona.scratch.act_description}"
  description += f" @ {persona.scratch.act_address}"

  execution = ret, persona.scratch.act_pronunciatio, description
  return execution















