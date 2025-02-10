import os
import aiohttp
from openai import AsyncOpenAI
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

# Database Configuration
DDN_SQL_URL= "https://destined-buck-3238.ddn.hasura.app/v1/sql"


class AIAssistant:
    def __init__(self, model: str):
        self.model = model
        if model == "anthropic":
            self.llm_key = os.getenv('ANTHROPIC_API_KEY')
        else:
            self.llm_key = os.getenv('OPENAI_API_KEY')
        self.client = aiohttp.ClientSession()
        self.messages = []
        self.api_responses = []
        
    def _prepare_payload(self, query: str) -> Dict[str, Any]:
        """Prepare the API payload from the conversation history"""
        return {
            "version": "v1",
            "promptql_api_key": os.getenv("PROMPTQL_SECRET_KEY"),  # Get from environment variable
            "llm": {
                "provider": self.model,
                "api_key": self.llm_key
            },
            "ddn": {
                "url": DDN_SQL_URL,
                "headers": {}
            },
            "artifacts": [],
            "system_instructions": "",  # Add system instructions if needed
            "timezone": "America/Los_Angeles",
            "interactions": self.messages,
            "stream": False
        }

    async def process_query(self, query: str) -> str:
        """Process a query using the API while maintaining conversation history"""
        try:
            interaction = {}
            
            # Add the new user query to conversation history
            interaction["user_message"] =  {
                "text": query
            }
            
            # Prepare the API payload
            payload = self._prepare_payload(query)
            payload["interactions"].append(interaction)
            
            print(f"\n[{datetime.now()}] waiting for llm response...")
            
            # Make the API call
            async with self.client.post( # type: ignore
                "https://api.promptql.pro.hasura.io/query", 
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {os.getenv('PROMPTQL_API_KEY')}"
                }
            ) as response:
                if response.status != 200:
                    error_msg = f"API request failed with status {response.status}"
                    logger.error(error_msg)
                    response_text = await response.text()
                    logger.error(f"Response: {response_text}")
                    raise Exception(error_msg)
                
                result = await response.json()
                
                print(json.dumps(result, indent=2))
                
                interaction.update(result)
                
                # Extract the assistant's response
                if result.get("assistant_actions"):
                    assistant_message = result.get("assistant_actions")[-1]["message"]
                else:
                    assistant_message = "No response received from the model"
                
                # Add the assistant's response to conversation history
                self.messages.append(interaction)
                
                return assistant_message

        except Exception as e:
            error_message = f"Error processing query: {str(e)}"
            logger.error(error_message)
            # Add error message to conversation history
            self.messages.append({"role": "assistant", "content": error_message})
            return error_message
        
    def clear_history(self):
        self.messages = []
        self.api_responses = []

    async def close(self):
        """Close all connections"""
        if self.client:
            await self.client.close()
            self.client = None


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model", type=str, default="anthropic", help="Model name (eg: hasura, anthropic, gpt-4o)"
    )
    parser.add_argument(
        "--api-key", type=str, default="", help="Model name (eg: hasura, anthropic, gpt-4o)"
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

            response = await assistant.process_query(query=query)
            print("\nModel's response:")
            print(response)

    except KeyboardInterrupt:
        print("\nExiting...")
        
    finally:
        await assistant.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
