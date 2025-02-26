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

from ai_assistant import AIAssistantResponse, ToolCallingAIAssistant

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
                stdin=subprocess.PIPE,
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

    @property
    def tool_schemas(self) -> List[Dict]:
        """Return the tool schemas in OpenAI format"""

        if self.has_python_tool:
            return [
                {
                    "name": "execute_python_program",
                    "description": "Run a Python program with optional data values passed as command line argument",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "pythonCode": {
                                "type": "string",
                                "description": "Python code to execute",
                            }
                        },
                        "required": ["pythonCode"],
                    },
                }
            ]
        else:
            return []


class AIAssistant(ToolCallingAIAssistant):
    def __init__(self, model: str, has_python_tool: bool):
        self.model = model
        self.has_python_tool = has_python_tool
        self.python_tool = DatabaseTool(has_python_tool=has_python_tool)
        self.client = anthropic.AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY")
        )

    async def process_query(self, query: str, artifacts: list) -> AIAssistantResponse:
        """Process a query using available tools and Claude while maintaining conversation history"""

        system_prompt = f"""
You are an AI assistant.

The user has uploaded the following files/artifacts for the conversation:

{artifacts}
        """

        messages = []
        api_responses = []
        response_text = None
        is_error = False

        messages.append({"role": "user", "content": query})

        tool_loop_count = 0
        MAX_TOOL_LOOPS = 10

        try:
            while tool_loop_count < MAX_TOOL_LOOPS:

                max_tokens = 64000 if self.model.startswith("claude-3-7") else 4096
                print(f"\n[{datetime.now()}] waiting for Anthropic response...")
                message = await self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=messages,
                    tools=self.python_tool.tool_schemas if self.has_python_tool else [],  # type: ignore
                )
                print(f"[{datetime.now()}] received Anthropic response...\n")
                api_responses.append(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "response": message.model_dump(),
                    }
                )

                # Check if the response contains tool use
                response_content = message.content
                if isinstance(response_content, list):
                    has_tool_calls = any(
                        block.type == "tool_use" for block in response_content
                    )
                else:
                    has_tool_calls = False

                if has_tool_calls:
                    tool_loop_count += 1
                    # Add assistant's response with structured content
                    messages.append({"role": "assistant", "content": response_content})

                    # Process all tool calls and collect results
                    tool_results = []
                    for content_block in response_content:
                        if content_block.type == "tool_use":
                            tool_call = content_block
                            function_name = tool_call.name
                            function_args = tool_call.input
                            tool_use_id = tool_call.id
                            assert isinstance(function_args, dict)
                            try:
                                result = None
                                if function_name == "execute_python_program":
                                    result = self.python_tool.execute_python_code(
                                        function_args.get("pythonCode", "")
                                    )

                                # Collect tool result
                                tool_results.append(
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": tool_use_id,
                                        "content": json.dumps(result),
                                    }
                                )
                            except Exception as e:
                                error_message = (
                                    f"Error executing {function_name}: {str(e)}"
                                )
                                logger.error(error_message)
                                tool_results.append(
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": tool_use_id,
                                        "content": json.dumps({"error": error_message}),
                                    }
                                )

                    # Add all tool results in a single message
                    messages.append({"role": "user", "content": tool_results})
                else:
                    # No tool calls, return the text content
                    final_content = ""
                    if isinstance(response_content, list):
                        text_blocks = [
                            block.text
                            for block in response_content
                            if block.type == "text"
                        ]
                        final_content = " ".join(text_blocks)

                    messages.append({"role": "assistant", "content": final_content})
                    response_text = final_content
                    break

                if tool_loop_count >= MAX_TOOL_LOOPS:
                    warning = "Maximum number of tool uses reached. Providing final response based on gathered information."
                    messages.append({"role": "assistant", "content": warning})
                    response_text = warning
            if response_text is None:
                response_text = "Too many tool calls"
        except Exception as e:
            error_message = f"Error processing query: {str(e)}"
            logger.error(error_message)
            messages.append({"role": "assistant", "content": error_message})
            response_text = error_message
            is_error = True
        return AIAssistantResponse(
            response=response_text,
            is_error=is_error,
            api_responses=api_responses,
            history=messages,
        )

    def process_response(self, response: AIAssistantResponse, tag_name: str) -> str:
        return extract_xml_tag_content(response.response, tag_name=tag_name)


def extract_xml_tag_content(xml_string, tag_name):
    pattern = f"<{tag_name}>(.*?)</{tag_name}>"
    match = re.search(pattern, xml_string, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


async def main():
    assistant = AIAssistant(model="claude-3-7-sonnet-latest", has_python_tool=False)

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

            response = await assistant.process_query(query, artifacts=[])
            print("\nClaude's response:")
            print(response)

    except KeyboardInterrupt:
        print("\nExiting...")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
