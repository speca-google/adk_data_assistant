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

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from . import tools
from .prompts import prompt_query_only, prompt_query_metadata
from .utils import get_env_var

from dotenv import load_dotenv
load_dotenv()

metadata_mode = get_env_var("BQ_METADATA_MODE")

logging.info(F"Metadata Mode: {metadata_mode}")

if metadata_mode == "ON":

    INSTRUCTIONS = prompt_query_metadata()
    TOOLS = [ 
        tools.get_metadata_description,
        tools.bq_nl2sql,
        tools.run_bigquery_validation,
    ]
else: 
    
    INSTRUCTIONS = prompt_query_only()
    TOOLS = [ 
        tools.bq_nl2sql,
        tools.run_bigquery_validation,
    ]


def setup_before_agent_call(callback_context: CallbackContext) -> None:
    """Setup the agent."""

    if "database_settings" not in callback_context.state:
        callback_context.state["database_settings"] = \
            tools.get_database_settings() 


root_agent = Agent(
    model=get_env_var("BQ_ROOT_MODEL"),
    name="bq_data_assistant",    
    instruction=INSTRUCTIONS,
    tools=TOOLS,
    before_agent_callback=setup_before_agent_call,
    generate_content_config=types.GenerateContentConfig(temperature=0.01),
)