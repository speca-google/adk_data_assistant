# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""BQ Data Assistant: get data from database (BigQuery) using NL2SQL."""

import logging
import yaml
from pathlib import Path

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from . import tools
from .prompts import build_prompt
from .utils import get_env_var

# Env Variables
from dotenv import load_dotenv
load_dotenv()

# Load agent config
script_dir = Path(__file__).parent.absolute()
config_path = script_dir / 'config.yaml'

with open(config_path, 'r') as f:
    config = yaml.safe_load(f)

# Print settings 
metadata_mode = config['settings']['metadata_mode']
logging.info(F"Metadata Mode: {metadata_mode}")

output_mode = config['settings']['output_mode']
logging.info(F"Output Mode: {output_mode}")


# Build the prompt instructions based on the modes selected
prompt_instructions = build_prompt(metadata_mode, output_mode)

# Selecting the tools based on metadata mode 
# This reinforce the Agent not use the metadata_description when metadata is disabled
if metadata_mode == "ON":
    TOOLS = [
        tools.get_metadata_description, 
        tools.bq_nl2sql, 
        tools.run_bigquery_validation
        ]
else: 
    TOOLS = [
        tools.bq_nl2sql,
        tools.run_bigquery_validation
        ]

def setup_before_agent_call(callback_context: CallbackContext) -> None:
    """Setup the agent."""

    if "database_settings" not in callback_context.state:
        callback_context.state["database_settings"] = \
            tools.get_database_settings() 

root_agent = Agent(
    model=get_env_var("AGENT_ROOT_MODEL"),
    name=config['agent_name'],    
    instruction=prompt_instructions,
    tools=TOOLS,
    before_agent_callback=setup_before_agent_call,
    generate_content_config=types.GenerateContentConfig(temperature=0.01),
)