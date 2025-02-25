import os
from openai import AsyncOpenAI
from typing import List, Dict, Any, Optional
import logging
import json
from datetime import datetime, date, timedelta
from decimal import Decimal
import tempfile
import subprocess
import argparse
import httpx
from ai_assistant import AIAssistantResponse, AIAssistantBase

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database Configuration
DDN_SQL_URL = "https://destined-buck-3238.ddn.hasura.app/v1/sql"


class AIAssistant(AIAssistantBase):
    def __init__(
        self, provider: str, model: Optional[str], initial_artifacts: List[Dict] = []
    ):
        self.provider = provider
        self.model = model
        if provider == "anthropic":
            self.llm_key = os.getenv("ANTHROPIC_API_KEY")
        else:
            self.llm_key = os.getenv("OPENAI_API_KEY")
        self.initial_artifacts = initial_artifacts

    def _prepare_payload(self) -> Dict[str, Any]:
        """Prepare the API payload from the conversation history"""
        return {
            "version": "v1",
            "promptql_api_key": os.getenv(
                "PROMPTQL_SECRET_KEY"
            ),  # Get from environment variable
            "llm": {
                "provider": self.provider,
                "api_key": self.llm_key,
                "model": self.model,
            },
            "ddn": {"url": DDN_SQL_URL, "headers": {}},
            "artifacts": self.initial_artifacts.copy(),
            "system_instructions": "- use cmp_to_key if writing a sorting algorithm focused on pairwise comparison",
            "timezone": "America/Los_Angeles",
            "interactions": [],
            "stream": False,
        }

    async def process_query(
        self, query: str, artifacts: list = []
    ) -> AIAssistantResponse:
        """Process a query using the API while maintaining conversation history"""
        history = []
        response_text = ""
        api_responses = []
        try:
            interaction = {}

            # Add the new user query to conversation history
            interaction["user_message"] = {"text": query}

            # Prepare the API payload
            payload = self._prepare_payload()
            payload["artifacts"].extend(artifacts)
            payload["interactions"].append(interaction)

            # Make the API call
            print(f"\n[{datetime.now()}] waiting for llm response...")
            async with httpx.AsyncClient(timeout=httpx.Timeout(5, read=600)) as client:
                try:
                    response = await client.post(
                        "https://api.promptql.pro.hasura.io/query",
                        # "http://localhost:5558/query",
                        json=payload,
                        headers={
                            "Content-Type": "application/json",
                        },
                    )
                    api_responses.append(response.text)
                    response.raise_for_status()

                    result = response.json()
                    api_responses[0] = result # Replace API response with deserialized JSON
                    interaction.update(result)

                    # Extract the assistant's response
                    if result.get("assistant_actions"):
                        assistant_message = result.get("assistant_actions")[-1][
                            "message"
                        ]
                    else:
                        assistant_message = "No response received from the model"

                    # Add the assistant's response to conversation history
                    history.append(interaction)

                    response_text = assistant_message

                except httpx.HTTPStatusError as e:
                    error_msg = (
                        f"API request failed with status {e.response.status_code}"
                    )
                    logger.error(error_msg)
                    logger.error(f"Response: {e.response.text}")
                    raise Exception(error_msg)
                except httpx.RequestError as e:
                    error_msg = f"API request failed: {repr(e)}"
                    logger.error(error_msg)
                    raise Exception(error_msg)

        except Exception as e:
            error_message = f"Error processing query: {str(e)}"
            logger.error(error_message)
            response_text = error_message

        return AIAssistantResponse(
            response=response_text, api_responses=[], history=history
        )

    def process_response(
        self, response: AIAssistantResponse, artifact_name: str, key: str | None = None
    ):
        last_found_artifact = None
        for interaction in response.history:
            # Check if the interaction has modified artifacts
            if modified_artifacts := interaction.get("modified_artifacts"):
                # Look for matching artifact_id
                for artifact in modified_artifacts:
                    if artifact.get("identifier") == artifact_name:
                        last_found_artifact = artifact

        if last_found_artifact is None:
            return None

        data = last_found_artifact.get("data")
        assert data is not None
        if key is None:
            return data
        else:
            return [{key: item[key]} for item in data]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider",
        type=str,
        default="anthropic",
        help="Model name (eg: anthropic, openai)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name (eg: o1, o3-mini)",
    )
    args = parser.parse_args()

    assistant = AIAssistant(provider=args.provider, model=args.model)

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
