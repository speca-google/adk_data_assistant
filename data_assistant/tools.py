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

"""This file contains the tools used by the database agent."""

import datetime
import logging
import re

from .utils import get_env_var
from google.adk.tools import ToolContext
from google.cloud import bigquery
from google.genai import Client


project_id = get_env_var("BQ_PROJECT_ID")
dataset_id = get_env_var("BQ_DATASET_ID")

llm_client = Client(vertexai=True, project=project_id)

MAX_NUM_ROWS = 80

database_settings = None
bq_client = None

def get_bq_client():
    """Get BigQuery client."""
    global bq_client
    if bq_client is None:
        bq_client = bigquery.Client(project=project_id)
    return bq_client


def get_database_settings():
    """Get database settings."""
    global database_settings
    if database_settings is None:
        database_settings = update_database_settings()
    return database_settings


def update_database_settings():
    """Update database settings."""
    global database_settings
    ddl_schema = get_bigquery_schema(
        dataset_id,
        client=get_bq_client(),
        project_id=project_id,
    )
    database_settings = {
        "bq_project_id": project_id,
        "bq_dataset_id": dataset_id,
        "bq_ddl_schema": ddl_schema
    }
    return database_settings


def get_bigquery_schema(dataset_id, client=None, project_id=None):
    """Retrieves schema and generates DDL with example values for a BigQuery dataset.

    Args:
        dataset_id (str): The ID of the BigQuery dataset (e.g., 'my_dataset').
        client (bigquery.Client): A BigQuery client.
        project_id (str): The ID of your Google Cloud Project.

    Returns:
        str: A string containing the generated DDL statements.
    """

    if client is None:
        client = bigquery.Client(project=project_id)

    # dataset_ref = client.dataset(dataset_id)
    dataset_ref = bigquery.DatasetReference(project_id, dataset_id)

    ddl_statements = ""

    for table in client.list_tables(dataset_ref):
        table_ref = dataset_ref.table(table.table_id)
        table_obj = client.get_table(table_ref)

        # Check if table is a view
        if table_obj.table_type != "TABLE":
            continue

        ddl_statement = f"CREATE OR REPLACE TABLE `{table_ref}` (\n"

        for field in table_obj.schema:
            ddl_statement += f"  `{field.name}` {field.field_type}"
            if field.mode == "REPEATED":
                ddl_statement += " ARRAY"
            if field.description:
                ddl_statement += f" COMMENT '{field.description}'"
            ddl_statement += ",\n"

        ddl_statement = ddl_statement[:-2] + "\n);\n\n"

        # Add example values if available (limited to first row)
        rows = client.list_rows(table_ref, max_results=5).to_dataframe()
        if not rows.empty:
            ddl_statement += f"-- Example values for table `{table_ref}`:\n"
            for _, row in rows.iterrows():  # Iterate over DataFrame rows
                ddl_statement += f"INSERT INTO `{table_ref}` VALUES\n"
                example_row_str = "("
                for value in row.values:  # Now row is a pandas Series and has values
                    if isinstance(value, str):
                        example_row_str += f"'{value}',"
                    elif value is None:
                        example_row_str += "NULL,"
                    else:
                        example_row_str += f"{value},"
                example_row_str = (
                    example_row_str[:-1] + ");\n\n"
                )  # remove trailing comma
                ddl_statement += example_row_str

        ddl_statements += ddl_statement

    return ddl_statements


def get_metadata_description(
    question: str,
    tool_context: ToolContext, # Use quotes if ToolContext is not yet defined
) -> str:
    """
    Analyzes the database schema to answer natural language questions about
    data location and structure (e.g., "Which table has X?", "Describe table Y.").
    It does NOT generate SQL.

    Args:
        question (str): The natural language metadata question.
        tool_context (ToolContext): The tool context containing the schema
                                     (tool_context.state["database_settings"]["bq_ddl_schema"]).

    Returns:
        str: A natural language answer to the metadata question.
    """
    ddl_schema = tool_context.state["database_settings"]["bq_ddl_schema"]

    prompt_template = """
    You are a data analyst expert. You are provided with BigQuery database schema (DDL statements with column comments).
    Your task is to answer the user's question about where to find certain information or about the structure of the tables, based *only* on the provided schema.
    Focus on identifying the most relevant table(s) and column(s) based on their names and, crucially, their descriptions (comments).

    **Schema:**
    ```
    {SCHEMA}
    ```

    **Question:**
    ```
    {QUESTION}
    ```

    **Instructions:**
    - Carefully examine the table names, column names, and especially the `COMMENT` associated with each column in the schema.
    - Provide a concise and direct natural language answer.
    - For example: "The information about customer addresses seems to be in the `project.dataset.customer_details` table, specifically in the `address_line1`, `city`, and `postal_code` columns. The `address_line1` column is described as 'Primary street address'."
    - If the question asks to describe a table, list its columns and their descriptions if available.
    - Do NOT generate SQL queries. Your output should be a natural language explanation.
    - If the schema does not seem to contain the information, state that.

    **Answer:**
    """

    prompt = prompt_template.format(SCHEMA=ddl_schema, QUESTION=question)

    # Consider using a specific model tuned for instruction following or QA if available,
    # otherwise, the NL2SQL model might also work if it's a general foundation model.
    model_to_use = get_env_var("AGENT_TOOL_MODEL")
    if not model_to_use:
        # Fallback or error if no model is defined
        return "Error: Model for metadata description not configured."

    response = llm_client.models.generate_content(
        model=model_to_use,
        contents=prompt,
        config={"temperature": 0.0}, # Low temperature for factual answers
    )

    answer = response.text.strip()
    tool_context.state["metadata_answer"] = answer
    # Ensure sql_query related states are cleared or set to None if this path is taken
    tool_context.state["sql_query"] = None
    tool_context.state["query_result"] = None

    print(f"\n[get_metadata_description] Question: {question}")
    print(f"[get_metadata_description] Answer: {answer}")
    return answer


def bq_nl2sql(
    question: str,
    tool_context: ToolContext,
) -> str:
    """Generates an initial SQL query from a natural language question.

    Args:
        question (str): Natural language question.
        tool_context (ToolContext): The tool context to use for generating the SQL
          query.

    Returns:
        str: An SQL statement to answer this question.
    """

    prompt_template = """
        You are a BigQuery SQL expert tasked with generating SQL queries in the GoogleSql dialect to answer user's questions that explicitly ask for data retrieval from BigQuery tables. If the question is about table structure or where to find data (a metadata question), you should indicate that this type of question is handled differently and avoid generating SQL.
        
        Your primary task is to write a BigQuery SQL query that answers the following data retrieval question while using the provided context.
        If the question is NOT about retrieving data (e.g., "which table has emails?", "describe table products"), output a message like: "This question appears to be about metadata. I am designed to generate SQL for data retrieval."

        **Guidelines:**

        - **Table Referencing:** Always use the full table name with the database prefix in the SQL statement.  Tables should be referred to using a fully qualified name with enclosed in backticks (`) e.g. `project_name.dataset_name.table_name`.  Table names are case sensitive.
        - **Joins:** Join as few tables as possible. When joining tables, ensure all join columns are the same data type. Analyze the database and the table schema provided to understand the relationships between columns and tables.
        - **Aggregations:**  Use all non-aggregated columns from the `SELECT` statement in the `GROUP BY` clause.
        - **SQL Syntax:** Return syntactically and semantically correct SQL for BigQuery with proper relation mapping (i.e., project_id, owner, table, and column relation). Use SQL `AS` statement to assign a new name temporarily to a table column or even a table wherever needed. Always enclose subqueries and union queries in parentheses.
        - **Column Usage:** Use *ONLY* the column names (column_name) mentioned in the Table Schema. Do *NOT* use any other column names. Associate `column_name` mentioned in the Table Schema only to the `table_name` specified under Table Schema.
        - **FILTERS:** You should write query effectively  to reduce and minimize the total rows to be returned. For example, you can use filters (like `WHERE`, `HAVING`, etc. (like 'COUNT', 'SUM', etc.) in the SQL query.
        - **LIMIT ROWS:**  The maximum number of rows returned should be less than {MAX_NUM_ROWS}.

        **Schema:**

        The database structure is defined by the following table schemas (possibly with sample rows):

        ```
        {SCHEMA}
        ```

        **Natural language question:**

        ```
        {QUESTION}
        ```

        **Think Step-by-Step:** Carefully consider the schema, question, guidelines, and best practices outlined above to generate the correct BigQuery SQL.

   """

    ddl_schema = tool_context.state["database_settings"]["bq_ddl_schema"]

    prompt = prompt_template.format(
        MAX_NUM_ROWS=MAX_NUM_ROWS, SCHEMA=ddl_schema, QUESTION=question
    )

    response = llm_client.models.generate_content(
        model=get_env_var("AGENT_TOOL_MODEL"),
        contents=prompt,
        config={"temperature": 0.1},
    )

    sql = response.text
    if sql:
        sql = sql.replace("```sql", "").replace("```", "").strip()
    
    # Add a check to see if the LLM decided it's a metadata question
    if "metadata" in sql.lower() and ("table has" in question.lower() or "describe table" in question.lower()): # Heuristic
        tool_context.state["sql_query"] = None
        tool_context.state["metadata_hint"] = sql # Store the hint
        # Return a specific indicator or the message itself,
        # so the orchestrator knows this isn't SQL.
        # For simplicity here, we'll let the main agent handle routing primarily.
        # It's better if the orchestrator LLM makes the routing decision upfront.
        # So, we'll assume bq_nl2sql is *always* expected to return SQL if called for SQL.
        # The main agent prompt (next section) will be key for routing.

        # Note: The main strategy will be for the orchestrator agent (using your main prompt) to decide which tool to call first. 
        # The change above is more of a safeguard or for advanced scenarios.
        

    print("\n sql:", sql)

    tool_context.state["sql_query"] = sql

    return sql


def run_bigquery_validation(
    sql_string: str,
    tool_context: ToolContext,
) -> str:
    """Validates BigQuery SQL syntax and functionality.

    This function validates the provided SQL string by attempting to execute it
    against BigQuery in dry-run mode. It performs the following checks:

    1. **SQL Cleanup:**  Preprocesses the SQL string using a `cleanup_sql`
    function
    2. **DML/DDL Restriction:**  Rejects any SQL queries containing DML or DDL
       statements (e.g., UPDATE, DELETE, INSERT, CREATE, ALTER) to ensure
       read-only operations.
    3. **Syntax and Execution:** Sends the cleaned SQL to BigQuery for validation.
       If the query is syntactically correct and executable, it retrieves the
       results.
    4. **Result Analysis:**  Checks if the query produced any results. If so, it
       formats the first few rows of the result set for inspection.

    Args:
        sql_string (str): The SQL query string to validate.
        tool_context (ToolContext): The tool context to use for validation.

    Returns:
        str: A message indicating the validation outcome. This includes:
             - "Valid SQL. Results: ..." if the query is valid and returns data.
             - "Valid SQL. Query executed successfully (no results)." if the query
                is valid but returns no data.
             - "Invalid SQL: ..." if the query is invalid, along with the error
                message from BigQuery.
    """

    def cleanup_sql(sql_string):
        """Processes the SQL string to get a printable, valid SQL string."""

        # 1. Remove backslashes escaping double quotes
        sql_string = sql_string.replace('\\"', '"')

        # 2. Remove backslashes before newlines (the key fix for this issue)
        sql_string = sql_string.replace("\\\n", "\n")  # Corrected regex

        # 3. Replace escaped single quotes
        sql_string = sql_string.replace("\\'", "'")

        # 4. Replace escaped newlines (those not preceded by a backslash)
        sql_string = sql_string.replace("\\n", "\n")

        # 5. Add limit clause if not present
        if "limit" not in sql_string.lower():
            sql_string = sql_string + " limit " + str(MAX_NUM_ROWS)

        return sql_string

    logging.info("Validating SQL: %s", sql_string)
    sql_string = cleanup_sql(sql_string)
    logging.info("Validating SQL (after cleanup): %s", sql_string)

    final_result = {"query_result": None, "error_message": None}

    # More restrictive check for BigQuery - disallow DML and DDL
    if re.search(
        r"(?i)(update|delete|drop|insert|create|alter|truncate|merge)", sql_string
    ):
        final_result["error_message"] = (
            "Invalid SQL: Contains disallowed DML/DDL operations."
        )
        return final_result

    try:
        query_job = get_bq_client().query(sql_string)
        results = query_job.result()  # Get the query results

        if results.schema:  # Check if query returned data
            rows = [
                {
                    key: (
                        value
                        if not isinstance(value, datetime.date)
                        else value.strftime("%Y-%m-%d")
                    )
                    for (key, value) in row.items()
                }
                for row in results
            ][
                :MAX_NUM_ROWS
            ]  # Convert BigQuery RowIterator to list of dicts
            # return f"Valid SQL. Results: {rows}"
            final_result["query_result"] = rows

            tool_context.state["query_result"] = rows

        else:
            final_result["error_message"] = (
                "Valid SQL. Query executed successfully (no results)."
            )

    except (
        Exception
    ) as e:  # Catch generic exceptions from BigQuery  # pylint: disable=broad-exception-caught
        final_result["error_message"] = f"Invalid SQL: {e}"

    print("\n run_bigquery_validation final_result: \n", final_result)

    return final_result