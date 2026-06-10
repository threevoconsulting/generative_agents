# Docker config template for the simulation backend.
#
# The Dockerfile copies this file to utils.py at image build time (utils.py
# itself is gitignored). The Anthropic API key is intentionally NOT stored here
# -- llm_provider reads ANTHROPIC_API_KEY from the environment -- so no secret
# is baked into the image. Pass it via docker-compose / Portainer instead.
import os

key_owner = os.environ.get("KEY_OWNER", "docker")

maze_assets_loc = "../../environment/frontend_server/static_dirs/assets"
env_matrix  = f"{maze_assets_loc}/the_ville/matrix"
env_visuals = f"{maze_assets_loc}/the_ville/visuals"

fs_storage      = "../../environment/frontend_server/storage"
fs_temp_storage = "../../environment/frontend_server/temp_storage"

collision_block_id = "32125"

debug = True
