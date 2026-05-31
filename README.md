

# Generative Agents: Interactive Simulacra of Human Behavior 

<p align="center" width="100%">
<img src="cover.png" alt="Smallville" style="width: 80%; min-width: 300px; display: block; margin: auto;">
</p>

This repository accompanies our research paper titled "[Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/abs/2304.03442)." It contains our core simulation module for  generative agents—computational agents that simulate believable human behaviors—and their game environment. Below, we document the steps for setting up the simulation environment on your local machine and for replaying the simulation as a demo animation.

## <img src="https://joonsungpark.s3.amazonaws.com:443/static/assets/characters/profile/Isabella_Rodriguez.png" alt="Generative Isabella">   Setting Up the Environment 
To set up your environment, you will need to generate a `utils.py` file that contains your OpenAI API key and download the necessary packages.

### Step 1. Generate Utils File
In the `reverie/backend_server` folder (where `reverie.py` is located), create a new file titled `utils.py` and copy and paste the content below into the file:
```
# Put your name
key_owner = "<Name>"

# --- LLM / embedding provider configuration ---------------------------------
# By default the simulation uses Anthropic's Claude for text generation and a
# local sentence-transformers model for embeddings (no embedding API cost).
# Provide your Anthropic API key here (or set the ANTHROPIC_API_KEY env var):
anthropic_api_key = "<Your Anthropic API Key>"

# To use OpenAI instead, set the following and provide an OpenAI key:
#   llm_provider = "openai"        # default: "claude"
#   embedding_backend = "openai"   # default: "local"
#   openai_api_key = "<Your OpenAI API Key>"
# ----------------------------------------------------------------------------

maze_assets_loc = "../../environment/frontend_server/static_dirs/assets"
env_matrix = f"{maze_assets_loc}/the_ville/matrix"
env_visuals = f"{maze_assets_loc}/the_ville/visuals"

fs_storage = "../../environment/frontend_server/storage"
fs_temp_storage = "../../environment/frontend_server/temp_storage"

collision_block_id = "32125"

# Verbose 
debug = True
```
Replace `<Your Anthropic API Key>` with your Anthropic API key, and `<name>` with your name.

#### Choosing models and providers
All LLM and embedding calls funnel through `reverie/backend_server/llm_provider.py`. Configuration is resolved with the precedence **environment variable > `utils.py` attribute > built-in default**, so you can override anything without editing code. The main knobs (with their defaults) are:

| Setting | Default | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER` | `claude` | Text provider: `claude`, `openai`, or `ollama` (local, free) |
| `EMBEDDING_BACKEND` | `local` | Embeddings: `local` (sentence-transformers) or `openai` |
| `CLAUDE_MODEL_CHEAP` | `claude-haiku-4-5-20251001` | High-frequency calls (perception, planning, action resolution) |
| `CLAUDE_MODEL_STRONG` | `claude-sonnet-4-6` | Conversation and reflection |
| `LOCAL_EMBED_MODEL` | `BAAI/bge-large-en-v1.5` | Local embedding model (better retrieval than the older `all-MiniLM-L6-v2`) |

The cognitive loop makes many low-judgment calls per step and only a few that benefit from a stronger model, so the cheap/strong tiering keeps cost down while preserving conversation quality.

> **Embedding compatibility note:** different embedding backends produce vectors of different dimensionality. It is only safe to *resume* a saved simulation with the same `EMBEDDING_BACKEND`/`LOCAL_EMBED_MODEL` it was created under. Base simulations ship with empty embedding stores, so starting a fresh simulation is always safe.

#### Running fully locally (no API cost) with Ollama
You can run the agents on a local model via [Ollama](https://ollama.com) instead of a paid API. Conversation quality is lower than Claude, but on a 32GB Apple-silicon Mac the defaults below give believable agents at a usable speed:

1. Install [Ollama](https://ollama.com) and pull the model (the default is tuned for a 32GB Mac):
   ```
   ollama pull qwen2.5:14b-instruct
   ```
   (For better conversations with more RAM, pull `qwen2.5:32b-instruct` and set `OLLAMA_MODEL_STRONG` to it.)
2. Point the backend at Ollama by setting one environment variable before starting `reverie.py`:
   ```
   export LLM_PROVIDER=ollama
   ```
   No `ANTHROPIC_API_KEY` is needed in this mode — generation runs on your machine.

> **Running the backend in Docker (e.g. on a Mac)?** Ollama runs on the *host*, the backend in the *container*, so two extra things are required — see [DOCKER.md → "Run locally with Ollama"](DOCKER.md). In short: start Ollama with `OLLAMA_HOST=0.0.0.0:11434 ollama serve` (so the container can reach it) and set the app's `OLLAMA_HOST=http://host.docker.internal:11434`.

| Setting | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL. **Running the backend in Docker on a Mac?** Set this to `http://host.docker.internal:11434` so the container can reach Ollama on the host. |
| `OLLAMA_MODEL_CHEAP` | `qwen2.5:14b-instruct` | High-frequency calls |
| `OLLAMA_MODEL_STRONG` | `qwen2.5:14b-instruct` | Conversation and reflection (bump to `qwen2.5:32b-instruct` for higher quality) |
| `OLLAMA_NUM_CTX` | `8192` | Context window; larger fits more retrieved memory per prompt (better grounding) at the cost of RAM/speed |
| `OLLAMA_REPEAT_PENALTY` | `1.1` | Curbs the repetitive looping small local models fall into |

Structured calls are sent with Ollama's `format: json` grammar constraint where applicable, which keeps small local models from breaking the formats the simulation parses. The local embedding model (`bge-large-en-v1.5`) runs in-process regardless of text provider, so memory retrieval stays free and high-quality.
 
### Step 2. Install requirements.txt
Install everything listed in the `requirements.txt` file (I strongly recommend first setting up a virtualenv as usual). A note on Python version: we tested our environment on Python 3.9.12. 

## <img src="https://joonsungpark.s3.amazonaws.com:443/static/assets/characters/profile/Klaus_Mueller.png" alt="Generative Klaus">   Running a Simulation 
To run a new simulation, you will need to concurrently start two servers: the environment server and the agent simulation server.

### Step 1. Starting the Environment Server
Again, the environment is implemented as a Django project, and as such, you will need to start the Django server. To do this, first navigate to `environment/frontend_server` (this is where `manage.py` is located) in your command line. Then run the following command:

    python manage.py runserver

Then, on your favorite browser, go to [http://localhost:8000/](http://localhost:8000/). If you see a message that says, "Your environment server is up and running," your server is running properly. Ensure that the environment server continues to run while you are running the simulation, so keep this command-line tab open! (Note: I recommend using either Chrome or Safari. Firefox might produce some frontend glitches, although it should not interfere with the actual simulation.)

### Step 2. Starting the Simulation Server
Open up another command line (the one you used in Step 1 should still be running the environment server, so leave that as it is). Navigate to `reverie/backend_server` and run `reverie.py`.

    python reverie.py
This will start the simulation server. A command-line prompt will appear, asking the following: "Enter the name of the forked simulation: ". To start a 3-agent simulation with Isabella Rodriguez, Maria Lopez, and Klaus Mueller, type the following:
    
    base_the_ville_isabella_maria_klaus
The prompt will then ask, "Enter the name of the new simulation: ". Type any name to denote your current simulation (e.g., just "test-simulation" will do for now).

    test-simulation
Keep the simulator server running. At this stage, it will display the following prompt: "Enter option: "

### Step 3. Running and Saving the Simulation
On your browser, navigate to [http://localhost:8000/simulator_home](http://localhost:8000/simulator_home). You should see the map of Smallville, along with a list of active agents on the map. You can move around the map using your keyboard arrows. Please keep this tab open. To run the simulation, type the following command in your simulation server in response to the prompt, "Enter option":

    run <step-count>
Note that you will want to replace `<step-count>` above with an integer indicating the number of game steps you want to simulate. For instance, if you want to simulate 100 game steps, you should input `run 100`. One game step represents 10 seconds in the game.


Your simulation should be running, and you will see the agents moving on the map in your browser. Once the simulation finishes running, the "Enter option" prompt will re-appear. At this point, you can simulate more steps by re-entering the run command with your desired game steps, exit the simulation without saving by typing `exit`, or save and exit by typing `fin`.

The saved simulation can be accessed the next time you run the simulation server by providing the name of your simulation as the forked simulation. This will allow you to restart your simulation from the point where you left off.

### Play Mode: living in the town
The simulation can run in two modes:

* **Simulation mode** (the default, described above) — the agents live out their lives with no human participant. Open `http://localhost:8000/simulator_home`.
* **Play mode** — you control a human avatar who lives in the town. The agents *perceive* you as a fellow resident and you can hold conversations with them. Open `http://localhost:8000/simulator_play` (optionally `?name=YourName` to set how the agents refer to you, e.g. `http://localhost:8000/simulator_play?name=Alex`).

In play mode:

* Move your avatar with the **arrow keys**; the camera follows you and you collide with walls and furniture.
* Your tile position is reported to the backend each step, so the agents see you and may form memories about you.
* Walk up to any resident and a **chat panel** (bottom-right) lets you talk to them. Type a message and press **Send**; press **End** to close the conversation (the agent then commits it to memory and will remember you next time).

Because the agents' replies are generated by the backend, a simulation must be **actively running** for them to respond — start a long run (e.g. `run 1000`) and interact while it proceeds. Conversation responses use the "strong" model tier (see the configuration table above).

#### Real-time updates (optional, recommended for play mode)
By default the browser exchanges state with the server by polling. If [Django Channels](https://channels.readthedocs.io/) is installed (it is included in `environment/frontend_server/requirements.txt`), the environment server automatically serves a WebSocket endpoint and the frontend uses it instead: movement updates and chat replies are *pushed* the instant they are ready, which makes play-mode conversations feel responsive. No configuration is needed — just run `python manage.py runserver` as usual. If Channels is not installed, everything still works via the original polling path.

### Step 4. Replaying a Simulation
You can replay a simulation that you have already run simply by having your environment server running and navigating to the following address in your browser: `http://localhost:8000/replay/<simulation-name>/<starting-time-step>`. Please make sure to replace `<simulation-name>` with the name of the simulation you want to replay, and `<starting-time-step>` with the integer time-step from which you wish to start the replay.

For instance, by visiting the following link, you will initiate a pre-simulated example, starting at time-step 1:  
[http://localhost:8000/replay/July1_the_ville_isabella_maria_klaus-step-3-20/1/](http://localhost:8000/replay/July1_the_ville_isabella_maria_klaus-step-3-20/1/)

### Step 5. Demoing a Simulation
You may have noticed that all character sprites in the replay look identical. We would like to clarify that the replay function is primarily intended for debugging purposes and does not prioritize optimizing the size of the simulation folder or the visuals. To properly demonstrate a simulation with appropriate character sprites, you will need to compress the simulation first. To do this, open the `compress_sim_storage.py` file located in the `reverie` directory using a text editor. Then, execute the `compress` function with the name of the target simulation as its input. By doing so, the simulation file will be compressed, making it ready for demonstration.

To start the demo, go to the following address on your browser: `http://localhost:8000/demo/<simulation-name>/<starting-time-step>/<simulation-speed>`. Note that `<simulation-name>` and `<starting-time-step>` denote the same things as mentioned above. `<simulation-speed>` can be set to control the demo speed, where 1 is the slowest, and 5 is the fastest. For instance, visiting the following link will start a pre-simulated example, beginning at time-step 1, with a medium demo speed:  
[http://localhost:8000/demo/July1_the_ville_isabella_maria_klaus-step-3-20/1/3/](http://localhost:8000/demo/July1_the_ville_isabella_maria_klaus-step-3-20/1/3/)

### Tips
We've noticed that OpenAI's API can hang when it reaches the hourly rate limit. When this happens, you may need to restart your simulation. For now, we recommend saving your simulation often as you progress to ensure that you lose as little of the simulation as possible when you do need to stop and rerun it. Running these simulations, at least as of early 2023, could be somewhat costly, especially when there are many agents in the environment.

## <img src="https://joonsungpark.s3.amazonaws.com:443/static/assets/characters/profile/Maria_Lopez.png" alt="Generative Maria">   Simulation Storage Location
All simulations that you save will be located in `environment/frontend_server/storage`, and all compressed demos will be located in `environment/frontend_server/compressed_storage`. 

## <img src="https://joonsungpark.s3.amazonaws.com:443/static/assets/characters/profile/Sam_Moore.png" alt="Generative Sam">   Customization

There are two ways to optionally customize your simulations. 

### Author and Load Agent History
First is to initialize agents with unique history at the start of the simulation. To do this, you would want to 1) start your simulation using one of the base simulations, and 2) author and load agent history. More specifically, here are the steps:

#### Step 1. Starting Up a Base Simulation 
There are two base simulations included in the repository: `base_the_ville_n25` with 25 agents, and `base_the_ville_isabella_maria_klaus` with 3 agents. Load one of the base simulations by following the steps until step 2 above. 

#### Step 2. Loading a History File 
Then, when prompted with "Enter option: ", you should load the agent history by responding with the following command:

    call -- load history the_ville/<history_file_name>.csv
Note that you will need to replace `<history_file_name>` with the name of an existing history file. There are two history files included in the repo as examples: `agent_history_init_n25.csv` for `base_the_ville_n25` and `agent_history_init_n3.csv` for `base_the_ville_isabella_maria_klaus`. These files include semicolon-separated lists of memory records for each of the agents—loading them will insert the memory records into the agents' memory stream.

#### Step 3. Further Customization 
To customize the initialization by authoring your own history file, place your file in the following folder: `environment/frontend_server/static_dirs/assets/the_ville`. The column format for your custom history file will have to match the example history files included. Therefore, we recommend starting the process by copying and pasting the ones that are already in the repository.

### Create New Base Simulations
For a more involved customization, you will need to author your own base simulation files. The most straightforward approach would be to copy and paste an existing base simulation folder, renaming and editing it according to your requirements. This process will be simpler if you decide to keep the agent names unchanged. However, if you wish to change their names or increase the number of agents that the Smallville map can accommodate, you might need to directly edit the map using the [Tiled](https://www.mapeditor.org/) map editor.


## <img src="https://joonsungpark.s3.amazonaws.com:443/static/assets/characters/profile/Eddy_Lin.png" alt="Generative Eddy">   Authors and Citation 

**Authors:** Joon Sung Park, Joseph C. O'Brien, Carrie J. Cai, Meredith Ringel Morris, Percy Liang, Michael S. Bernstein

Please cite our paper if you use the code or data in this repository. 
```
@inproceedings{Park2023GenerativeAgents,  
author = {Park, Joon Sung and O'Brien, Joseph C. and Cai, Carrie J. and Morris, Meredith Ringel and Liang, Percy and Bernstein, Michael S.},  
title = {Generative Agents: Interactive Simulacra of Human Behavior},  
year = {2023},  
publisher = {Association for Computing Machinery},  
address = {New York, NY, USA},  
booktitle = {In the 36th Annual ACM Symposium on User Interface Software and Technology (UIST '23)},  
keywords = {Human-AI interaction, agents, generative AI, large language models},  
location = {San Francisco, CA, USA},  
series = {UIST '23}
}
```

## <img src="https://joonsungpark.s3.amazonaws.com:443/static/assets/characters/profile/Wolfgang_Schulz.png" alt="Generative Wolfgang">   Acknowledgements

We encourage you to support the following three amazing artists who have designed the game assets for this project, especially if you are planning to use the assets included here for your own project: 
* Background art: [PixyMoon (@_PixyMoon\_)](https://twitter.com/_PixyMoon_)
* Furniture/interior design: [LimeZu (@lime_px)](https://twitter.com/lime_px)
* Character design: [ぴぽ (@pipohi)](https://twitter.com/pipohi)

In addition, we thank Lindsay Popowski, Philip Guo, Michael Terry, and the Center for Advanced Study in the Behavioral Sciences (CASBS) community for their insights, discussions, and support. Lastly, all locations featured in Smallville are inspired by real-world locations that Joon has frequented as an undergraduate and graduate student---he thanks everyone there for feeding and supporting him all these years.


