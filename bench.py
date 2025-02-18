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


class InputVariations(BaseModel):
    name: str
    parameters: Dict[str, Any]
    ground_truth_path: str


class OracleData(BaseModel):
    identifier: str
    title: str
    data_filepath: str


class InputConfig(BaseModel):
    promptql_prompt: str
    tool_calling_prompt: str
    oracle_prompt: str
    oracle_system_prompt: str
    oracle_data_list: Optional[List[OracleData]] = None
    result_artifact_name: Optional[str] = None
    result_artifact_key: Optional[str] = None
    result_tag_name: Optional[str] = None
    ground_truth_path: Optional[str] = None
    variations: Optional[List[InputVariations]] = None
    repeat: Optional[int] = None


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
    def __init__(self, ai_assistant, input_config: InputConfig, output_dir: str):
        self.assistant = ai_assistant
        self.output_dir = output_dir
        self.input_config = input_config

    def save_results(
        self,
        variation_name: str,
        run_index: int,
        response: str,
        elapsed_time: timedelta,
    ):
        """Save query results to output directory"""
        base_filename = f"{self.output_dir}/{variation_name}_run_{run_index}"

        os.makedirs(self.output_dir, exist_ok=True)

        # Save main output
        with open(f"{base_filename}.result", "w") as f:
            f.write(response)

        # Save conversation history
        with open(f"{base_filename}.history", "w") as f:
            json.dump(self.assistant.messages, f, indent=2, default=str)

        # Save actual API responses
        with open(f"{base_filename}.api", "w") as f:
            json.dump(self.assistant.api_responses, f, indent=2, default=str)

        with open(f"{base_filename}.time", "w") as f:
            f.write(f"{elapsed_time}")

    def should_skip(self, variation_name: str, run_index: int) -> bool:
        """Check if output already exists"""
        output_file = Path(self.output_dir) / f"{variation_name}_run_{run_index}.result"
        return output_file.exists()

    async def process_query(self, query: str) -> str:
        """Process a single query with given parameters"""
        self.assistant.clear_history()
        # query = query_template.format(k=run_info['topk'], n=run_info['lastn'])
        response = await self.assistant.process_query(query)

        return self.process_response(response)

    def process_response(self, response: str) -> str:
        processed_response = ""

        if isinstance(self.assistant, PromptQLAssistant):
            processed_response = json.dumps(
                self.assistant.process_response(
                    response,
                    self.input_config.result_artifact_name,
                    self.input_config.result_artifact_key,
                ),
                indent=2,
            )
        else:
            processed_response = self.assistant.process_response(
                response, self.input_config.result_tag_name
            )

        return processed_response

    async def run(self, input_filepath: str):
        """Main processing loop"""
        try:
            # Determine query template based on system
            query_template = (
                self.input_config.promptql_prompt
                if isinstance(self.assistant, PromptQLAssistant)
                else self.input_config.tool_calling_prompt
            )

            # Handle variations or default case
            variations = self.input_config.variations or [
                InputVariations(
                    name="default",
                    parameters={},
                    ground_truth_path=self.input_config.ground_truth_path,
                )
            ]

            for variation in variations:
                # Format query with parameters (empty dict for default case)
                query = query_template.format(**variation.parameters)

                # Determine number of runs
                num_runs = self.input_config.repeat if self.input_config.repeat else 1

                for run_index in range(1, num_runs + 1):
                    # Log processing status
                    param_info = (
                        f" with params: {variation.parameters}"
                        if variation.parameters
                        else ""
                    )
                    print(f"Processing {input_filepath} run {run_index}{param_info}")

                    # Skip if output exists
                    if self.should_skip(variation.name, run_index):
                        print(
                            f"Skipping existing output for run {run_index}{param_info}"
                        )
                        continue

                    # Process query and measure time
                    start_time = datetime.now()
                    response = await self.process_query(query=query)
                    elapsed_time = datetime.now() - start_time

                    print(f"TOTAL PROCESSING TIME: {elapsed_time} seconds")
                    self.save_results(variation.name, run_index, response, elapsed_time)

        except Exception as e:
            print(traceback.format_exc())
            print(f"Error during processing: {e}")


async def run(
    input_filepath: str,
    system: Literal["promptql", "tool_calling", "tool_calling_python"],
    oracle: bool,
    model: str,
    output_dir: str,
):
    input_config = read_input(input_filepath)
    output_dir = f"{output_dir}/{system}/{model}"
    if oracle:
        output_dir += "/oracle"
    if system == "promptql":
        if oracle:
            artifacts = []
            if input_config.oracle_data_list:
                for oracle_data in input_config.oracle_data_list:
                    absolute_file_path = resolve_relative_path(
                        file_path=oracle_data.data_filepath,
                        config_filepath=input_filepath,
                    )
                    artifacts.append(
                        {
                            "identifier": oracle_data.identifier,
                            "title": oracle_data.title,
                            "artifact_type": "table",
                            "data": json.loads(read_file_content(absolute_file_path)),
                        }
                    )
            else:
                print("no artifacts given")
                exit(1)

            processor = QueryProcessor(
                PromptQLAssistant(model, initial_artifacts=artifacts),  # type: ignore
                input_config=input_config,
                output_dir=output_dir,
            )
        else:
            processor = QueryProcessor(
                PromptQLAssistant(model),
                input_config=input_config,
                output_dir=output_dir,
            )
    elif not oracle:
        has_python_tool = system == "tool_calling_python"
        if model == "o1":
            processor = QueryProcessor(
                OpenAIAssistant("o1", has_python_tool=has_python_tool),
                input_config=input_config,
                output_dir=output_dir,
            )
        elif model == "o3-mini":
            processor = QueryProcessor(
                OpenAIAssistant("o3-mini", has_python_tool=has_python_tool),
                input_config=input_config,
                output_dir=output_dir,
            )
        elif model == "anthropic":
            processor = QueryProcessor(
                ClaudeAssistant(has_python_tool=has_python_tool),
                input_config=input_config,
                output_dir=output_dir,
            )
        else:
            print("unknown model")
            exit(1)
    elif system == "oracle":
        # If oracle_files is specified, read and format the system prompt
        file_contents = {}
        if input_config.oracle_data_list:
            for oracle_data in input_config.oracle_data_list:
                absolute_file_path = resolve_relative_path(
                    file_path=oracle_data.data_filepath, config_filepath=input_filepath
                )
                file_contents[oracle_data.identifier] = read_file_content(
                    absolute_file_path
                )

        # Format the system prompt with file contents
        oracle_system_prompt = input_config.oracle_system_prompt.format(**file_contents)
        has_python_tool = system == "tool_calling_python"
        if model == "o1":
            processor = QueryProcessor(
                OpenAIOracleAssistant(
                    "o1",
                    has_python_tool=has_python_tool,
                    system_prompt=oracle_system_prompt,
                ),
                input_config=input_config,
                output_dir=output_dir,
            )
        elif model == "o3-mini":
            processor = QueryProcessor(
                OpenAIOracleAssistant(
                    "o3-mini",
                    has_python_tool=has_python_tool,
                    system_prompt=oracle_system_prompt,
                ),
                input_config=input_config,
                output_dir=output_dir,
            )
        elif model == "anthropic":
            processor = QueryProcessor(
                ClaudeOracleAssistant(
                    has_python_tool=has_python_tool, system_prompt=oracle_system_prompt
                ),
                input_config=input_config,
                output_dir=output_dir,
            )
        else:
            print("unknown model")
            exit(1)

    else:
        print("unknown system")
        exit(1)
    await processor.run(input_filepath)


async def main():
    import argparse

    SYSTEM_CHOICES = ["promptql", "tool_calling", "tool_calling_python"]
    MODEL_CHOICES = ["anthropic", "o1", "o3-mini"]

    parser = argparse.ArgumentParser(description="Process queries using AI Assistant")
    parser.add_argument("--input_filepath", help="Input query file path", required=True)
    parser.add_argument("--output_dir", help="Output directory path", required=True)
    parser.add_argument(
        "--model",
        help="LLM to use",
        required=True,
        choices=MODEL_CHOICES,
    )
    parser.add_argument(
        "--system",
        help="System to evaluate",
        required=True,
        choices=SYSTEM_CHOICES,
    )
    parser.add_argument("--oracle", help="Use oracle data", action="store_true")
    parser.add_argument("--all", help="Run all configurations", action="store_true")

    args = parser.parse_args()

    if args.all:
        for system in SYSTEM_CHOICES:
            for model in MODEL_CHOICES:
                for oracle in [False, True]:
                    await run(
                        args.input_filepath,
                        system,
                        oracle,
                        model,
                        args.output_dir,
                    )
    else:
        await run(
            args.input_filepath, args.system, args.oracle, args.model, args.output_dir
        )


if __name__ == "__main__":
    asyncio.run(main())
