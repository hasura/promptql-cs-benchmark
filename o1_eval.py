import os
import psycopg2
from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
)
from typing import List, Dict, Any
import logging
import json
from datetime import datetime, date, timedelta
from decimal import Decimal
import tempfile
import subprocess
import argparse
import re

from ai_assistant import AIAssistantResponse, ToolCallingAIAssistant

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database Configuration
CONTROL_PLANE_URL = "postgresql://postgres:postgres@localhost:5432/control_plane_new"
SUPPORT_TICKETS_URL = (
    "postgresql://postgres:postgres@localhost:5432/support_tickets_new"
)


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder for handling datetime and Decimal objects"""

    def default(self, o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, timedelta):
            return f"{o.seconds} seconds"
        return super().default(o)


class DatabaseTool:
    def __init__(self, has_python_tool: bool = False):
        # Initialize database connections
        self.control_plane_conn = psycopg2.connect(CONTROL_PLANE_URL)
        self.support_tickets_conn = psycopg2.connect(SUPPORT_TICKETS_URL)
        self.has_python_tool = has_python_tool
        self.schema_cache = {}

    def get_database_schema(
        self, conn: psycopg2.extensions.connection, custom_where_clause: str
    ) -> str:
        """Get database schema information"""
        with conn.cursor() as cursor:
            query = """
                SELECT 
                    table_name,
                    column_name,
                    data_type
                FROM 
                    information_schema.columns
                WHERE 
                    table_schema = 'public' AND {}
                ORDER BY 
                    table_name, ordinal_position;
            """.format(
                custom_where_clause
            )

            cursor.execute(query)
            results = cursor.fetchall()

            schema = {}
            for row in results:
                table_name, column_name, data_type = row
                if table_name not in schema:
                    schema[table_name] = {"columns": []}
                schema[table_name]["columns"].append(
                    {"name": column_name, "type": data_type}
                )

            schema_str = "\n"
            for table, details in schema.items():
                schema_str += f"table {table} columns ("
                for col in details["columns"]:
                    schema_str += f" {col['name']} {col['type']},"
                schema_str += ")\n"

            return schema_str.strip()

    def execute_query(
        self, conn: psycopg2.extensions.connection, sql: str
    ) -> List[Dict]:
        """Execute a read-only SQL query"""

        logger.info("Executing SQL: \n %s", sql)
        with conn.cursor() as cursor:
            try:
                cursor.execute("BEGIN TRANSACTION READ ONLY")
                cursor.execute(sql)
                description = cursor.description
                assert description is not None
                columns = [desc[0] for desc in description]
                results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                conn.rollback()
                return results
            except Exception as e:
                conn.rollback()
                raise e

    @property
    def tool_schemas(self) -> list[ChatCompletionToolParam]:
        """Return the tool schemas in OpenAI format"""
        tools: list[ChatCompletionToolParam] = [
            {
                "type": "function",
                "function": {
                    "name": "query_control_plane_data",
                    "description": "Run a read-only SQL query against the control plane database and return the result",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sql": {
                                "type": "string",
                                "description": "SQL query to execute",
                            }
                        },
                        "required": ["sql"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "query_support_tickets",
                    "description": "Run a read-only SQL query against the support tickets database and return the result",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sql": {
                                "type": "string",
                                "description": "SQL query to execute",
                            }
                        },
                        "required": ["sql"],
                    },
                },
            },
        ]

        if self.has_python_tool:
            python_tool: ChatCompletionToolParam = {
                "type": "function",
                "function": {
                    "name": "execute_python_program",
                    "description": "Run a Python program. Output will be printed in stdout",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pythonCode": {
                                "type": "string",
                                "description": "Python code to execute",
                            }
                        },
                        "required": ["pythonCode"],
                    },
                },
            }
            tools.append(python_tool)

        return tools

    def execute_python_code(self, python_code: str) -> Dict[str, str]:
        """Execute Python code and return the results"""

        logger.info("Executing Python: \n %s", python_code)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
            tmp.write(python_code)
            tmp_path = tmp.name

        try:
            process = subprocess.Popen(
                ["python3", tmp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = process.communicate()
            return {
                "stdout": stdout,
                "stderr": stderr,
                "exitCode": str(process.returncode),
            }
        finally:
            os.unlink(tmp_path)

    def close(self):
        """Close database connections"""
        self.control_plane_conn.close()
        self.support_tickets_conn.close()


class AIAssistant(ToolCallingAIAssistant):
    def __init__(self, model: str = "o1", has_python_tool: bool = False):
        self.model = model
        self.tools = DatabaseTool(has_python_tool)
        self.client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        # Cache schemas on initialization
        self.control_plane_schema = self.tools.get_database_schema(
            self.tools.control_plane_conn, "table_name NOT LIKE 'support%'"
        )
        self.support_tickets_schema = self.tools.get_database_schema(
            self.tools.support_tickets_conn, "table_name LIKE 'support%'"
        )
        # Initialize conversation history with system message
        self.init_messages: list[ChatCompletionMessageParam] = [
            {
                "role": "system",
                "content": f"""You are an assistant with access to two databases with the following schemas:

1. Control Plane Database Schema:
{self.control_plane_schema}

2. Support Tickets Database Schema:
{self.support_tickets_schema}

Additional Instructions:

- Always write queries that are compatible with PostgreSQL
- Current timestamp is: {datetime.now()}
- Use tools provided to get the actual answer and don't stop with the theoretical plan
""",
            }
        ]

    async def process_query(self, query: str, artifacts: list) -> AIAssistantResponse:
        """Process a query using available tools and GPT-4 while maintaining conversation history"""

        assert len(artifacts) == 0, "Don't support artifacts"

        messages = self.init_messages.copy()
        api_responses = []
        response_text = None

        # Add the new user query to the conversation history
        messages.append({"role": "user", "content": query})
        tool_loop_count = 0
        MAX_TOOL_LOOPS = 10

        try:
            while tool_loop_count < MAX_TOOL_LOOPS:
                print(f"\n[{datetime.now()}] waiting for llm response...")
                completion = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.tools.tool_schemas,
                    tool_choice="auto",
                )
                print(f"[{datetime.now()}] received llm response...\n")
                assert completion.usage is not None
                print(
                    f"Model: {completion.model} Usage: {completion.usage.model_dump()}"
                )

                # Store the API response
                api_responses.append(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "response": completion.model_dump(),
                    }
                )

                assistant_message = completion.choices[0].message

                if not assistant_message.tool_calls:
                    # Add the assistant's response to conversation history
                    messages.append(
                        {
                            "role": "assistant",
                            "content": assistant_message.content or "",
                        }
                    )
                    response_text = assistant_message.content or ""

                # Add assistant message with tool calls to conversation history
                messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_message.content or "",
                        "tool_calls": assistant_message.tool_calls,
                    }  # type: ignore
                )
                tool_calls = (
                    assistant_message.tool_calls if assistant_message.tool_calls else []
                )
                if len(tool_calls) > 0:
                    tool_loop_count += 1
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)

                    result = None
                    error_message = None

                    try:
                        if function_name == "query_control_plane_data":
                            result = self.tools.execute_query(
                                self.tools.control_plane_conn,
                                function_args.get("sql", ""),
                            )
                        elif function_name == "query_support_tickets":
                            result = self.tools.execute_query(
                                self.tools.support_tickets_conn,
                                function_args.get("sql", ""),
                            )
                        elif function_name == "execute_python_program":
                            result = self.tools.execute_python_code(
                                function_args.get("pythonCode", "")
                            )
                    except Exception as e:
                        error_message = f"Error executing {function_name}: {str(e)}"
                        logger.error(error_message)
                        result = {"error": error_message}

                    # Add tool response to conversation history
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": function_name,
                            "content": json.dumps(
                                result, indent=2, cls=DateTimeEncoder
                            ),
                        }  # type: ignore
                    )

                if tool_loop_count >= MAX_TOOL_LOOPS:
                    # Add max tool use warning to conversation history
                    messages.append(
                        {
                            "role": "user",
                            "content": "You have reached the maximum number of tool uses. Please provide a final response based on the information you have gathered so far.",
                        }
                    )

            final_completion = await self.client.chat.completions.create(
                model=self.model, messages=messages
            )

            # Store the final API response
            api_responses.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "response": final_completion.model_dump(),
                }
            )

            final_response = final_completion.choices[0].message.content or ""
            # Add final response to conversation history
            messages.append({"role": "assistant", "content": final_response})
            response_text = final_response

        except Exception as e:
            error_message = f"Error processing query: {str(e)}"
            logger.error(error_message)
            # Add error message to conversation history
            messages.append({"role": "assistant", "content": error_message})
            response_text = error_message

        return AIAssistantResponse(
            response=response_text, api_responses=api_responses, history=messages
        )

    def process_response(self, response: AIAssistantResponse, tag_name: str) -> str:
        return str(extract_xml_tag_content(response.response, tag_name=tag_name))

    async def close(self):
        """Close all connections"""
        self.tools.close()


def extract_xml_tag_content(xml_string, tag_name):
    pattern = f"<{tag_name}>(.*?)</{tag_name}>"
    match = re.search(pattern, xml_string, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model", type=str, default="o3-mini", help="Model name (eg: o1, o3-mini)"
    )
    args = parser.parse_args()

    assistant = AIAssistant(model=args.model)

    try:
        while True:
            print("\nEnter your question (or 'quit' to exit)")
            print(
                "Use Ctrl+D (Unix) or Ctrl+Z (Windows) on an empty line to finish multi-line input"
            )
            print("---")

            lines = []
            try:
                while True:
                    line = input()

                    # Check for quit command after each line
                    if line.lower().strip() == "quit":
                        return

                    if not line and not lines:
                        continue
                    lines.append(line)
            except EOFError:
                pass

            query = "\n".join(lines).strip()

            if not query:
                continue

            response = await assistant.process_query(query=query, artifacts=[])
            print("\nModel's response:")
            print(response)

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        await assistant.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
