#!/usr/bin/env python3
import os
import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional, NamedTuple
import importlib.util
from dataclasses import dataclass
import pandas as pd
import yaml
from pydantic import BaseModel
import traceback

from bench import InputConfig


def read_input_config(filepath: str) -> InputConfig:
    """Read and validate input config from YAML file"""
    try:
        with open(filepath) as f:
            data = yaml.safe_load(f)
            return InputConfig.model_validate(data)
    except Exception as e:
        raise Exception(f"Failed to read config file: {e}")


@dataclass
class EvaluationResult:
    system: str
    model: str
    variation: str
    run: int
    score: float
    oracle: bool


class PathInfo(NamedTuple):
    system: str
    model: str
    oracle: bool
    variation: str
    run: int


def read_file_content(file_path: str) -> str:
    """Read and return the content of a file."""
    try:
        with open(file_path, "r") as file:
            return file.read()
    except Exception as e:
        raise Exception(f"Error reading file {file_path}: {str(e)}")


def find_result_files(base_dir: Path) -> List[Path]:
    """Find all .result files recursively in the given directory."""
    return list(base_dir.rglob("*.result"))


def parse_output_path(file_path: Path) -> PathInfo:
    """
    Parse output path to extract metadata.
    Expected format: {output_dir}/{model}/{system}/{retrieval|oracle}/{variation_name}_run_{run_index}.result
    """
    parts = list(file_path.parts)

    # Start from the end and work backwards
    filename = parts[-1]
    variation_name, run_part = filename.replace(".result", "").rsplit("_run_", 1)
    run_index = int(run_part)

    oracle = parts[-2] == "oracle"
    system = parts[-3]
    model = parts[-4]

    return PathInfo(
        system=system,
        model=model,
        oracle=oracle,
        variation=variation_name,
        run=run_index,
    )


def evaluate_directory(
    base_dir: Path, config: InputConfig, config_path: str, evaluator_func
) -> List[EvaluationResult]:
    """Evaluate all result files in the directory."""
    results = []
    result_files = find_result_files(base_dir)

    # Create mapping of variation names to ground truth paths
    ground_truth_paths = {}
    if config.variations:
        for variation in config.variations:
            ground_truth_paths[variation.name] = variation.ground_truth_path

    for file_path in result_files:
        try:
            # Parse path to get metadata
            path_info = parse_output_path(file_path)

            # Get ground truth path from config
            if path_info.variation not in ground_truth_paths:
                print(
                    f"Warning: No ground truth path found for variation {path_info.variation}"
                )
                continue

            ground_truth_path = ground_truth_paths[path_info.variation]

            # Handle relative paths - assume relative to config directory
            if not os.path.isabs(ground_truth_path):
                config_dir = os.path.dirname(os.path.abspath(config_path))
                ground_truth_path = os.path.join(config_dir, ground_truth_path)

            if not os.path.exists(ground_truth_path):
                print(f"Warning: Ground truth file not found: {ground_truth_path}")
                continue

            # Evaluate
            ground_truth = read_file_content(ground_truth_path)
            test_result = read_file_content(str(file_path))
            score = evaluator_func(ground_truth, test_result)
            print(f"TEST FILE: {str(file_path)}, SCORE: {score}")
            # Store result
            result = EvaluationResult(
                system=path_info.system,
                model=path_info.model,
                variation=path_info.variation,
                run=path_info.run,
                score=score,
                oracle=path_info.oracle,
            )
            results.append(result)

        except Exception as e:
            print(f"Error processing {file_path}: {str(e)}")
            continue

    return results


def save_results(results: List[EvaluationResult], output_path: Path):
    import csv

    # Define the fieldnames based on the dataclass fields
    fieldnames = ["model", "system", "oracle", "variation", "run", "score"]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        # Write each result as a row
        for r in results:
            writer.writerow(
                {
                    "model": r.model,
                    "system": r.system,
                    "oracle": r.oracle,
                    "variation": r.variation,
                    "run": r.run,
                    "score": r.score,
                }
            )

    print(f"\nDetailed results saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate results against ground truth"
    )
    parser.add_argument(
        "--input_config", type=str, help="Path to input config YAML file", required=True
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        help="Base output directory containing results",
        required=True,
    )
    parser.add_argument(
        "--evaluator_module",
        type=str,
        help="Python module containing evaluate_score function",
        required=True,
    )
    parser.add_argument(
        "--results-file",
        type=str,
        default="evaluation-results.csv",
        help="Path to save summary statistics (default: evaluation_summary.csv)",
    )

    args = parser.parse_args()

    try:
        # Load config
        input_config = read_input_config(args.input_config)

        # Load evaluator module
        spec = importlib.util.spec_from_file_location(
            "evaluator", args.evaluator_module
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load module: {args.evaluator_module}")

        evaluator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(evaluator)

        if not hasattr(evaluator, "evaluate_score"):
            raise ImportError("Module does not contain evaluate_score function")

        # Process directory
        base_dir = Path(args.output_dir)
        results = evaluate_directory(
            base_dir, input_config, args.input_config, evaluator.evaluate_score
        )

        save_results(results, Path(args.results_file))

    except Exception as e:
        print(traceback.format_exc())
        print(f"Error: {str(e)}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
