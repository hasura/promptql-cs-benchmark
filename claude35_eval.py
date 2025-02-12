import os
import psycopg2
import anthropic
from anthropic.types import TextBlock
from typing import List, Dict, Any
import logging
import json
from datetime import datetime, date
from decimal import Decimal
import tempfile
import subprocess
import re

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
        """Return the tool schemas in Anthropic format"""
        return [
            {
                "name": "query_control_plane_data",
                "description": "Run a read-only SQL query against the control plane database",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "SQL query to execute"
                        }
                    },
                    "required": ["sql"]
                }
            },
            {
                "name": "query_support_tickets",
                "description": "Run a read-only SQL query against the support tickets database",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "SQL query to execute"
                        }
                    },
                    "required": ["sql"]
                }
            },
            # {
            #     "name": "execute_python_program",
            #     "description": "Run a Python program with optional data values passed as command line argument",
            #     "input_schema": {
            #         "type": "object",
            #         "properties": {
            #             "pythonCode": {
            #                 "type": "string",
            #                 "description": "Python code to execute"
            #             },
            #             "dataValues": {
            #                 "type": "string",
            #                 "description": "JSON string of data values"
            #             }
            #         },
            #         "required": ["pythonCode"]
            #     }
            # }
        ]

    def close(self):
        """Close database connections"""
        self.control_plane_conn.close()
        self.support_tickets_conn.close()

class AIAssistant:
    def __init__(self):
        self.db_tool = DatabaseTool()
        self.client = anthropic.AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY")
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
        self.system_prompt = f"""You are an assistant with access to two databases with the following schemas:

1. Control Plane Database Schema:
{self.control_plane_schema}

2. Support Tickets Database Schema:
{self.support_tickets_schema}

Additional Instructions:
- Always write queries that are compatible with PostgreSQL
- Current timestamp is: {datetime.now()}
"""
        self.messages = []
        self.api_responses = []

    async def process_query(self, query: str) -> str:
        """Process a query using available tools and Claude while maintaining conversation history"""
        self.messages.append({"role": "user", "content": query})
    
        tool_loop_count = 0
        MAX_TOOL_LOOPS = 10

        try:
            while tool_loop_count < MAX_TOOL_LOOPS:
                message = await self.client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=4096,
                    system=self.system_prompt,
                    messages=self.messages,
                    tools=self.db_tool.tool_schemas
                )

                self.api_responses.append({
                    "timestamp": datetime.now().isoformat(),
                    "response": message.model_dump()
                })

                # Check if the response contains tool use
                response_content = message.content
                if isinstance(response_content, list):
                    has_tool_calls = any(block.type == "tool_use" for block in response_content)
                else:
                    has_tool_calls = False

                if has_tool_calls:
                    tool_loop_count += 1
                    # Add assistant's response with structured content
                    self.messages.append({
                        "role": "assistant",
                        "content": response_content
                    })
                
                    # Process all tool calls and collect results
                    tool_results = []
                    for content_block in response_content:
                        if content_block.type == "tool_use":
                            tool_call = content_block
                            function_name = tool_call.name
                            function_args = tool_call.input
                            tool_use_id = tool_call.id
                    
                            try:
                                result = None
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
                                # elif function_name == "execute_python_program":
                                #     result = execute_python_code(
                                #         function_args.get("pythonCode", ""),
                                #         function_args.get("dataValues", "[]")
                                #     )
                        
                                # Collect tool result
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": tool_use_id,
                                    "content": json.dumps(result, cls=DateTimeEncoder)
                                })
                            except Exception as e:
                                error_message = f"Error executing {function_name}: {str(e)}"
                                logger.error(error_message)
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": tool_use_id,
                                    "content": json.dumps({"error": error_message})
                                })
                
                    # Add all tool results in a single message
                    self.messages.append({
                        "role": "user",
                        "content": tool_results
                    })
                else:
                    # No tool calls, return the text content
                    final_content = ""
                    if isinstance(response_content, list):
                        text_blocks = [block.text for block in response_content 
                                    if block.type == "text"]
                        final_content = " ".join(text_blocks)
            
                    self.messages.append({
                        "role": "assistant",
                        "content": final_content
                    })
                    return final_content

                if tool_loop_count >= MAX_TOOL_LOOPS:
                    warning = "Maximum number of tool uses reached. Providing final response based on gathered information."
                    self.messages.append({
                        "role": "assistant",
                        "content": warning
                    })
                    return warning

        except Exception as e:
            error_message = f"Error processing query: {str(e)}"
            logger.error(error_message)
            self.messages.append({
                "role": "assistant",
                "content": error_message
            })
            return error_message

    def clear_history(self):
        """Clear conversation history"""
        self.messages = []
        self.api_responses = []
        
    def process_response(self, response: str, tag_name: str) -> str | None:
        return extract_xml_tag_content(response, tag_name=tag_name)

    async def close(self):
        """Close all connections"""
        self.db_tool.close()

def extract_xml_tag_content(xml_string, tag_name):
    pattern = f"<{tag_name}>(.*?)</{tag_name}>"
    match = re.search(pattern, xml_string, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None

def execute_python_code(python_code: str, data_values: str = "[]") -> Dict[str, str|int]:
    """Execute Python code and return the results"""
    
    logger.info("Executing Python: \n %s", python_code)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
        tmp.write(python_code)
        tmp_path = tmp.name

    try:
        process = subprocess.Popen(
            ['python3', tmp_path, data_values],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate()
        return {
            "stdout": stdout,
            "stderr": stderr,
            "exitCode": process.returncode
        }
    finally:
        os.unlink(tmp_path)

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
            print("\nClaude's response:")
            print(response)
            
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        await assistant.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())