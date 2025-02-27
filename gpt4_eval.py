# type: ignore
import os
import psycopg2
from openai import AsyncOpenAI
from typing import List, Dict, Any
import logging
import json
from datetime import datetime, date
from decimal import Decimal
import tempfile
import subprocess

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database Configuration
CONTROL_PLANE_URL = "postgresql://postgres:postgres@localhost:5432/control_plane_new"
SUPPORT_TICKETS_URL = "postgresql://postgres:postgres@localhost:5432/support_tickets_new"

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder for handling datetime and Decimal objects"""
    def default(self, o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)

class DatabaseTool:
    def __init__(self):
        # Initialize database connections
        self.control_plane_conn = psycopg2.connect(CONTROL_PLANE_URL)
        self.support_tickets_conn = psycopg2.connect(SUPPORT_TICKETS_URL)
        self.schema_cache = {}

    def get_database_schema(self, conn: psycopg2.extensions.connection, custom_where_clause: str) -> str:
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
            """.format(custom_where_clause)
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            schema = {}
            for row in results:
                table_name, column_name, data_type = row
                if table_name not in schema:
                    schema[table_name] = {'columns': []}
                schema[table_name]['columns'].append({
                    'name': column_name,
                    'type': data_type
                })
            
            schema_str = '\n'
            for table, details in schema.items():
                schema_str += f"table {table} columns ("
                for col in details['columns']:
                    schema_str += f" {col['name']} {col['type']},"
                schema_str += ')\n'
                
            return schema_str.strip()

    def execute_query(self, conn: psycopg2.extensions.connection, sql: str) -> List[Dict]:
        """Execute a read-only SQL query"""
        
        logger.info("Executing SQL: \n %s", sql)
        with conn.cursor() as cursor:
            try:
                cursor.execute("BEGIN TRANSACTION READ ONLY")
                cursor.execute(sql)
                columns = [desc[0] for desc in cursor.description]
                results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                conn.rollback()
                return results
            except Exception as e:
                conn.rollback()
                raise e

    @property
    def tool_schemas(self) -> List[Dict]:
        """Return the tool schemas in OpenAI format"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "query_control_plane_data",
                    "description": "Run a read-only SQL query against the control plane database",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sql": {
                                "type": "string",
                                "description": "SQL query to execute"
                            }
                        },
                        "required": ["sql"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "query_support_tickets",
                    "description": "Run a read-only SQL query against the support tickets database",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sql": {
                                "type": "string",
                                "description": "SQL query to execute"
                            }
                        },
                        "required": ["sql"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_python_program",
                    "description": "Run a Python program with optional data values passed as command line argument. The results should be printed in stdout or stderr",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pythonCode": {
                                "type": "string",
                                "description": "Python code to execute"
                            },
                            "dataValues": {
                                "type": "string",
                                "description": "JSON string of data values"
                            }
                        },
                        "required": ["pythonCode"]
                    }
                }
            }
        ]

    def close(self):
        """Close database connections"""
        self.control_plane_conn.close()
        self.support_tickets_conn.close()

class AIAssistant:
    def __init__(self):
        self.db_tool = DatabaseTool()
        self.client = AsyncOpenAI(
            api_key=os.environ.get("OPENAI_API_KEY")
        )
        # Cache schemas on initialization
        self.control_plane_schema = self.db_tool.get_database_schema(
            self.db_tool.control_plane_conn,
            "table_name NOT LIKE 'support%'"
        )
        self.support_tickets_schema = self.db_tool.get_database_schema(
            self.db_tool.support_tickets_conn,
            "table_name LIKE 'support%'"
        )
        # Initialize conversation history with system message
        self.init_messages = [{
            "role": "system",
            "content": f"""You are an assistant with access to two databases with the following schemas:

1. Control Plane Database Schema:
{self.control_plane_schema}

2. Support Tickets Database Schema:
{self.support_tickets_schema}

Additional Instructions:

- Always write queries that are compatible with PostgreSQL
- Use cmp_to_key if writing a sorting algorithm focused on pairwise comparison.
"""
        }]
        self.messages = self.init_messages.copy() 
        self.api_responses = []

    def clear_history(self):
        self.messages = self.init_messages.copy()
        self.api_responses = []

    async def process_query(self, query: str) -> str:
        """Process a query using available tools and GPT-4 while maintaining conversation history"""
        # Add the new user query to the conversation history
        self.messages.append({"role": "user", "content": query})
        
        tool_loop_count = 0
        MAX_TOOL_LOOPS = 10

        try:
            while tool_loop_count < MAX_TOOL_LOOPS:
                completion = await self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=self.messages,
                    tools=self.db_tool.tool_schemas,
                    tool_choice="auto"
                )

                # Store the API response
                self.api_responses.append({
                    "timestamp": datetime.now().isoformat(),
                    "response": completion.model_dump()
                })
                                
                assistant_message = completion.choices[0].message

                if not assistant_message.tool_calls:
                    # Add the assistant's response to conversation history
                    self.messages.append({
                        "role": "assistant",
                        "content": assistant_message.content or ""
                    })
                    return assistant_message.content or ""

                # Add assistant message with tool calls to conversation history
                self.messages.append({
                    "role": "assistant",
                    "content": assistant_message.content or "",
                    "tool_calls": assistant_message.tool_calls
                })

                if len(assistant_message.tool_calls) > 0:
                    tool_loop_count += 1
                for tool_call in assistant_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    result = None
                    error_message = None
                    
                    try:
                        if function_name == "query_control_plane_data":
                            result = self.db_tool.execute_query(
                                self.db_tool.control_plane_conn,
                                function_args.get("sql", "")
                            )
                        elif function_name == "query_support_tickets":
                            result = self.db_tool.execute_query(
                                self.db_tool.support_tickets_conn,
                                function_args.get("sql", "")
                            )
                        elif function_name == "execute_python_program":
                            result = execute_python_code(
                                function_args.get("pythonCode", ""),
                                function_args.get("dataValues", "[]")
                            )
                    except Exception as e:
                        error_message = f"Error executing {function_name}: {str(e)}"
                        logger.error(error_message)
                        result = {"error": error_message}

                    # Add tool response to conversation history
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": json.dumps(result, indent=2, cls=DateTimeEncoder)
                    })

                if tool_loop_count >= MAX_TOOL_LOOPS:
                    # Add max tool use warning to conversation history
                    self.messages.append({
                        "role": "user",
                        "content": "You have reached the maximum number of tool uses. Please provide a final response based on the information you have gathered so far."
                    })

            final_completion = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=self.messages
            )
            
            # Store the final API response
            self.api_responses.append({
                "timestamp": datetime.now().isoformat(),
                "response": final_completion.model_dump()
            })
                                        
            final_response = final_completion.choices[0].message.content or ""
            # Add final response to conversation history
            self.messages.append({
                "role": "assistant",
                "content": final_response
            })
            return final_response 

        except Exception as e:
            error_message = f"Error processing query: {str(e)}"
            logger.error(error_message)
            # Add error message to conversation history
            self.messages.append({
                "role": "assistant",
                "content": error_message
            })
            return error_message

    def close(self):
        """Close all connections"""
        self.db_tool.close()

def execute_python_code(python_code: str, data_values: str = "[]") -> Dict[str, str | int]:
    """Execute Python code and return the results."""
    
    logger.info("Executing Python code:\n%s", python_code)

    # Ensure we clean up the temporary file in all cases
    tmp_file = None
    try:
        # Create a temporary file to store the Python code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as tmp:
            tmp.write(python_code)
            tmp_file = tmp.name  # Save the file path for later use

        # Execute the Python code in a subprocess
        process = subprocess.Popen(
            ['python3', tmp_file, data_values],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate()

        # Return the output and error streams along with the exit code
        return {
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
            "exitCode": process.returncode
        }

    except Exception as e:
        logger.error("Error while executing Python code: %s", str(e))
        return {
            "stdout": "",
            "stderr": str(e),
            "exitCode": 1
        }

    finally:
        # Clean up the temporary file
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.unlink(tmp_file)
            except Exception as e:
                logger.warning("Failed to delete temporary file: %s", str(e))
        

async def main():
    assistant = AIAssistant()
    
    try:
        while True:
            print("\nEnter your question (or 'quit' to exit)")
            print("Use Ctrl+D (Unix) or Ctrl+Z (Windows) on an empty line to finish multi-line input")
            print("---")
            
            lines = []
            try:
                while True:
                    line = input()
                    
                    # Check for quit command after each line
                    if line.lower().strip() == 'quit':
                        return
                        
                    if not line and not lines:
                        continue
                    lines.append(line)
            except EOFError:
                pass
            
            query = '\n'.join(lines).strip()
            
            if not query:
                continue
            
            response = await assistant.process_query(query)
            print("\nGPT's response:")
            print(response)
            
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        assistant.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())