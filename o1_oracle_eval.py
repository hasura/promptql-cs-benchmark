import os
from openai import AsyncOpenAI
import re
from typing import List, Dict, Any
import logging
import json
from datetime import datetime, date, timedelta
from decimal import Decimal
import tempfile
import subprocess
import argparse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseTool:

    def __init__(self, has_python_tool: bool = False):
        self.has_python_tool = has_python_tool

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
            return {"stdout": stdout, "stderr": stderr, "exitCode": process.returncode}
        finally:
            os.unlink(tmp_path)

    @property
    def tool_schemas(self) -> List[Dict]:
        """Return the tool schemas in OpenAI format"""

        if self.has_python_tool:
            return [
                {
                    "type": "function",
                    "function": {
                        "name": "execute_python_program",
                        "description": "Run a Python program. The results should be printed in stdout.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "pythonCode": {
                                    "type": "string",
                                    "description": "Python code to execute"
                                }
                            },
                            "required": ["pythonCode"]
                        }
                    }
                }
            ]
        else:
            return []

class AIAssistant:
    def __init__(self, model, has_python_tool):
        self.model = model
        self.has_python_tool = has_python_tool
        self.python_tool = DatabaseTool(has_python_tool=has_python_tool)
        self.client = AsyncOpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"), timeout=3600)
        # Initialize conversation history with system message
        self.init_messages = [
            {
                "role": "system",
                "content": "TODO" 
            }
        ]
        self.messages = self.init_messages.copy()
        self.api_responses = []

    def clear_history(self):
        self.messages = self.init_messages.copy()
        self.api_responses = []

    async def process_query(self, query: str, artifacts: list) -> str:
        """Process a query using available tools and GPT-4 while maintaining conversation history"""
        # Add the new user query to the conversation history
        self.messages.append({"role": "user", "content": query})
        tool_loop_count = 0
        MAX_TOOL_LOOPS = 10

        try:
            while tool_loop_count < MAX_TOOL_LOOPS:
                print(f"\n[{datetime.now()}] waiting for llm response...")
                if self.has_python_tool:
                    completion = await self.client.chat.completions.create(
                        model=self.model,
                        messages=self.messages,
                        tools=self.python_tool.tool_schemas,
                        tool_choice="auto",
                    )
                else:
                    completion = await self.client.chat.completions.create(
                        model=self.model,
                        messages=self.messages
                    )

                print(f"[{datetime.now()}] received llm response...\n")
                print(
                    f"Model: {completion.model} Usage: {completion.usage.model_dump()}"
                )

                # Store the API response
                self.api_responses.append(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "response": completion.model_dump(),
                    }
                )

                assistant_message = completion.choices[0].message

                if not assistant_message.tool_calls:
                    # Add the assistant's response to conversation history
                    self.messages.append(
                        {
                            "role": "assistant",
                            "content": assistant_message.content or "",
                        }
                    )
                    return assistant_message.content or ""

                # Add assistant message with tool calls to conversation history
                self.messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_message.content or "",
                        "tool_calls": assistant_message.tool_calls,
                    }
                )
                if len(assistant_message.tool_calls) > 0:
                    tool_loop_count += 1
                for tool_call in assistant_message.tool_calls:

                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)

                    result = None
                    error_message = None

                    try:
                        if function_name == "execute_python_program":
                            result = self.python_tool.execute_python_code(
                                function_args.get("pythonCode", ""),
                            )
                    except Exception as e:
                        error_message = f"Error executing {function_name}: {str(e)}"
                        logger.error(error_message)
                        result = {"error": error_message}

                    # Add tool response to conversation history
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": function_name,
                            "content": json.dumps(
                                result, indent=2
                            ),
                        }
                    )

                if tool_loop_count >= MAX_TOOL_LOOPS:
                    # Add max tool use warning to conversation history
                    self.messages.append(
                        {
                            "role": "user",
                            "content": "You have reached the maximum number of tool uses. Please provide a final response based on the information you have gathered so far.",
                        }
                    )

            final_completion = await self.client.chat.completions.create(
                model=self.model,
                messages=self.messages
            )

            # Store the final API response
            self.api_responses.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "response": final_completion.model_dump(),
                }
            )

            final_response = final_completion.choices[0].message.content or ""
            # Add final response to conversation history
            self.messages.append(
                {"role": "assistant", "content": final_response})
            return final_response

        except Exception as e:
            error_message = f"Error processing query: {str(e)}"
            logger.error(error_message)
            # Add error message to conversation history
            self.messages.append(
                {"role": "assistant", "content": error_message})
            return error_message
        
    def process_response(self, response: str, tag_name: str) -> str | None:
        return extract_xml_tag_content(response, tag_name=tag_name)

def extract_xml_tag_content(xml_string, tag_name):
    pattern = f"<{tag_name}>(.*?)</{tag_name}>"
    match = re.search(pattern, xml_string, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model", type=str, default="o1", help="Model name (eg: o1, o3-mini)"
    )

    parser.add_argument(
        "--support_tickets", type=str, default="support_ticket.json", help="path to support tickets"
    )

    parser.add_argument(
        "--support_ticket_comments", type=str, default="support_ticket_comment.json", help="path to support ticket comments"
    )
    args = parser.parse_args()

    with open(args.support_tickets, 'r') as file:
        support_tickets = file.read()

    with open(args.support_ticket_comments, 'r') as file:
        support_ticket_comments = file.read()

    with open('empty_file.json', 'r') as file:
        user_data = file.read()

    assistant = AIAssistant(model=args.model, has_python_tool=args.with_python_tool, system_prompt=system_prompt)

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

            response = await assistant.process_query(query=query)
            print("\nModel's response:")
            print(response)

    except KeyboardInterrupt:
        print("\nExiting...")

if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
