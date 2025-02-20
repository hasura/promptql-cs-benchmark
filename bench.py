from enum import Enum
import json
import asyncio
import os
from pathlib import Path
from typing import List, Dict, Any, Literal, Optional
from pydantic import BaseModel
import yaml
from datetime import datetime, timedelta
from o1_eval import AIAssistant as OpenAIAssistant
from claude35_eval import AIAssistant as ClaudeAssistant
from promptql_eval import AIAssistant as PromptQLAssistant
from o1_oracle_eval import AIAssistant as OpenAIOracleAssistant
from claude35_oracle_eval import AIAssistant as ClaudeOracleAssistant
import traceback
from ai_assistant import AIAssistantResponse, AIAssistantBase, ToolCallingAIAssistant


class System(str, Enum):
    PROMPTQL = "promptql"
    TOOL_CALLING = "tool_calling"
    TOOL_CALLING_PYTHON = "tool_calling_python"


class Model(str, Enum):
    CLAUDE = "claude"
    O1 = "o1"
    O3_MINI = "o3-mini"


class InputVariations(BaseModel):
    name: str
    parameters: Dict[str, Any]
    ground_truth_path: str
    oracle_data_file_paths: List[str]


class PromptQlInputConfig(BaseModel):
    retrieval_prompt: str
    oracle_prompt: str
    result_artifact_name: str
    result_artifact_key: str


class ToolCallingInputConfig(BaseModel):
    retrieval_prompt: str
    oracle_prompt: str
    result_tag_name: str


class InputConfig(BaseModel):
    promptql: PromptQlInputConfig
    tool_calling: ToolCallingInputConfig
    variations: List[InputVariations]


def read_file_content(file_path: str) -> str:
    """Read and return the content of a file."""
    try:
        with open(file_path, "r") as file:
            return json.dumps(json.load(file), indent=2)
    except Exception as e:
        raise Exception(f"Error reading file {file_path}: {str(e)}")


def resolve_relative_path(file_path: str, config_filepath: str) -> str:
    # Get the absolute directory of the config file
    config_dir = os.path.dirname(os.path.abspath(config_filepath))

    # Join paths and normalize (this handles '..' properly)
    absolute_path = os.path.normpath(os.path.join(config_dir, file_path))

    return absolute_path


def read_input(filepath: str) -> InputConfig:
    """Read and validate query from YAML file"""
    try:
        with open(filepath) as f:
            data = yaml.safe_load(f)
            return InputConfig.model_validate(data)
    except Exception as e:
        raise Exception(f"Failed to read query file: {e}")


class QueryProcessor:
    def __init__(
        self,
        ai_assistant: AIAssistantBase,
        input_config: InputConfig,
        output_dir: str,
        repeat: int,
        oracle: bool,
    ):
        self.assistant = ai_assistant
        self.output_dir = output_dir
        self.input_config = input_config
        self.repeat = repeat
        self.oracle = oracle

    def save_results(
        self,
        variation_name: str,
        run_index: int,
        response: AIAssistantResponse,
        elapsed_time: timedelta,
    ):
        """Save query results to output directory"""
        base_filename = f"{self.output_dir}/{variation_name}_run_{run_index}"

        os.makedirs(self.output_dir, exist_ok=True)

        # Save main output
        with open(f"{base_filename}.result", "w") as f:
            f.write(self.process_response(response))

        # Save conversation history
        with open(f"{base_filename}.history", "w") as f:
            json.dump(response.history, f, indent=2, default=str)

        # Save actual API responses
        with open(f"{base_filename}.api", "w") as f:
            json.dump(response.api_responses, f, indent=2, default=str)

        with open(f"{base_filename}.time", "w") as f:
            f.write(f"{elapsed_time}")

    def should_skip(self, variation_name: str, run_index: int) -> bool:
        """Check if output already exists"""
        output_file = Path(self.output_dir) / f"{variation_name}_run_{run_index}.result"
        return output_file.exists()

    def process_response(self, response: AIAssistantResponse) -> str:
        processed_response = ""

        if isinstance(self.assistant, PromptQLAssistant):
            processed_response = json.dumps(
                self.assistant.process_response(
                    response,
                    self.input_config.promptql.result_artifact_name,
                    self.input_config.promptql.result_artifact_key,
                ),
                indent=2,
            )
        else:
            assert isinstance(self.assistant, ToolCallingAIAssistant)
            processed_response = self.assistant.process_response(
                response, self.input_config.tool_calling.result_tag_name
            )

        return processed_response

    async def run_impl(
        self,
        input_filepath: str,
        query: str,
        variation: InputVariations,
        run_index: int,
        wait: int,
    ):
        await asyncio.sleep(wait)

        # Process query and measure time
        start_time = datetime.now()
        artifacts = []

        if self.oracle:
            for relative_file_path in variation.oracle_data_file_paths:
                absolute_file_path = resolve_relative_path(
                    file_path=relative_file_path,
                    config_filepath=input_filepath,
                )
                artifacts.append(json.loads(read_file_content(absolute_file_path)))

        response = await self.assistant.process_query(query=query, artifacts=artifacts)
        elapsed_time = datetime.now() - start_time

        print(f"TOTAL PROCESSING TIME: {elapsed_time} seconds")
        self.save_results(variation.name, run_index, response, elapsed_time)

    async def run(self, input_filepath: str):
        """Main processing loop"""
        try:
            # Determine query template based on system
            if isinstance(self.assistant, PromptQLAssistant):
                if self.oracle:
                    query_template = self.input_config.promptql.oracle_prompt
                else:
                    query_template = self.input_config.promptql.retrieval_prompt
            else:
                if self.oracle:
                    query_template = self.input_config.tool_calling.oracle_prompt
                else:
                    query_template = self.input_config.tool_calling.retrieval_prompt

            # Handle variations or default case
            variations = self.input_config.variations

            tasks = []
            for variation in variations:
                # Format query with parameters (empty dict for default case)
                query = query_template.format(**variation.parameters)

                for run_index in range(1, self.repeat + 1):
                    # Log processing status
                    param_info = (
                        f" with params: {variation.parameters}" if variation.parameters else ""
                    )
                    print(f"Processing {input_filepath} run {run_index}{param_info}")

                    # Skip if output exists
                    if self.should_skip(variation.name, run_index):
                        print(f"Skipping existing output for run {run_index}{param_info}")
                        continue

                    tasks.append(
                        self.run_impl(
                            input_filepath=input_filepath,
                            query=query,
                            variation=variation,
                            run_index=run_index,
                            wait=len(tasks)
                            * 30,  # Wait 30 seconds per task to avoid overload
                        )
                    )

            await asyncio.gather(*tasks)

        except Exception as e:
            print(traceback.format_exc())
            print(f"Error during processing: {e}")


async def run(
    input_filepath: str,
    system: System,
    oracle: bool,
    model: Model,
    output_dir: str,
    repeat: int,
):
    input_config = read_input(input_filepath)
    output_dir = f"{output_dir}/{model.value}/{system.value}"
    if oracle:
        output_dir += "/oracle"
    else:
        output_dir += "/retrieval"
    if system == System.PROMPTQL:
        match model:
            case Model.O1 | Model.O3_MINI:
                promptql_llm_provider = "openai"
                promptql_llm_model = model.value
            case Model.CLAUDE:
                promptql_llm_provider = "anthropic"
                promptql_llm_model = None

        assistant = PromptQLAssistant(promptql_llm_provider, promptql_llm_model)
    else:
        has_python_tool = system == System.TOOL_CALLING_PYTHON

        match model:
            case Model.O1 | Model.O3_MINI:
                assistant = (OpenAIOracleAssistant if oracle else OpenAIAssistant)(
                    model.value, has_python_tool=has_python_tool
                )
            case Model.CLAUDE:
                assistant = (ClaudeOracleAssistant if oracle else ClaudeAssistant)(
                    has_python_tool=has_python_tool
                )

    processor = QueryProcessor(
        assistant,
        input_config=input_config,
        output_dir=output_dir,
        repeat=repeat,
        oracle=oracle,
    )

    await processor.run(input_filepath)


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Process queries using AI Assistant")
    parser.add_argument("--input_filepath", help="Input query file path", required=True)
    parser.add_argument("--output_dir", help="Output directory path", required=True)
    parser.add_argument(
        "--model",
        type=Model,
        help="LLM to use",
        required=False,
        choices=list(Model),
    )
    parser.add_argument(
        "--system",
        type=System,
        help="System to evaluate",
        required=False,
        choices=list(System),
    )
    parser.add_argument("--oracle", help="Use oracle data", action="store_true")
    parser.add_argument("--all", help="Run all configurations", action="store_true")
    parser.add_argument("--repeat", help="Number of runs", type=int, default=3)

    args = parser.parse_args()

    if args.all:
        tasks = [
            run(
                args.input_filepath, system, oracle, model, args.output_dir, args.repeat
            )
            for system in System
            for model in Model
            # for oracle in [False, True]
            for oracle in [False]
        ]
        await asyncio.gather(*tasks)
    else:
        await run(
            args.input_filepath,
            args.system,
            args.oracle,
            args.model,
            args.output_dir,
            args.repeat,
        )


if __name__ == "__main__":
    asyncio.run(main())
