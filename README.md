# BigQuery Data Assistant

### Overview 

Simple agent for NL2SQL on BigQuery Dataset 

 - Config to allow the Agent answer metadata questions (BQ_METADATA_MODE="ON") on Env File
 - Notebook Jupyter with the step-by-step to deploy this agente on Agent Engine (GCP) and Link to Agentspace

This agent was based on Data Science Agent from ADK Examples. 
For more examples, see: https://github.com/google/adk-samples

## Installation 

We recommend creating a virtual Python environment using venv:

```shell
python -m venv .venv
```

Now, you can activate the virtual environment using the appropriate command for your operating system and environment:

```shell
# Mac / Linux
source .venv/bin/activate

# Windows CMD:
.venv\Scripts\activate.bat

# Windows PowerShell:
.venv\Scripts\Activate.ps1
```

Install the requirements

```shell
pip install -r requirements.txt
```

## Configuring and running local 

Before deploy this agent on Agent Engine and Agentspace it is important running localy and see if it works. 

For that (and also for deployment) there are few cofiguration steps: 

#### Settings on Config.yaml file

*This config file (config.yaml) contains info about the Agent, Settings and Deploy dependencies (this is important to the Agent Engine Deploy).*

```yaml
agent_name: 'data_assistant'
agent_display_name: 'Data Assistant'
agent_description: 'Useful data assistant to perform NL2SQL and answer metadata questions'

settings:
  metadata_mode: 'ON' # "ON" for include Metadata answering mode or "OFF" for query only 
  output_mode: 'SIMPLE' # "DETAILED" for return a json with four keys explaining the reasoning, sql_query, sql_results and answer. or "SIMPLE" for simple answer

deploy:
  dependencies: ['google-cloud-aiplatform[agent_engines]', 'google-adk', 'cloudpickle', 'pydantic', 'google-cloud-bigquery', 'pandas', 'db-dtypes', 'pyyaml']
```

#### Settings on .env file

Some configuration about the dataset and enviroment like *BQ Project ID*, *BQ Dataset ID*, *Agent Root Model*, and *Agent Tool Model* are configured as Enviroment Variables due to the possibility to change between deployments. 

file: .env.example (rename it to .env and fill the information).

```shell
# Env Variables for Vertex AI 
GOOGLE_GENAI_USE_VERTEXAI="True"
GOOGLE_CLOUD_PROJECT="" # Project ID from GCP (where Agent is going to run)
GOOGLE_CLOUD_LOCATION="" # Location

# BigQuery DatasetID 
BQ_PROJECT_ID=""  # BigQuery Project ID
BQ_DATASET_ID="" # BigQuery Dataset ID

# Models for the assistant
AGENT_ROOT_MODEL="" # Model as "gemini-2.5-flash-preview-04-17"
AGENT_TOOL_MODEL=""  # Model as "gemini-2.0-flash"
```


## Running Locally

Try runinng local using adk web: 
```shell
adk web
```

Autentication: if ask for authentication run: 
```shell
gcloud auth application-default login
```
Obs.: This will running trhough your gcloud auth login user



## Deploy on Agent Engine and Agentspace

To deploy this Agent on Agent Engine and Agentspace, follow this notebook: 
[deploy_agent.ipynb](deploy_agent.ipynb)
