#!/usr/bin/env python3
import os
import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import importlib.util
from dataclasses import dataclass
import pandas as pd
import yaml
from pydantic import BaseModel
import traceback


class InputVariations(BaseModel):
    name: str
    parameters: Dict[str, Any]
    ground_truth_path: str


class InputConfig(BaseModel):
    promptql_prompt: str
    tool_calling_prompt: str
    oracle_prompt: str
    oracle_system_prompt: str
    oracle_files: Optional[Dict[str,str]] = None
    result_artifact_name: Optional[str] = None
    result_artifact_key: Optional[str] = None
    result_tag_name: Optional[str] = None
    ground_truth_path: Optional[str] = None
    variations: Optional[List[InputVariations]] = None
    repeat: Optional[int] = None


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
    with_python: bool


def find_result_files(base_dir: Path) -> List[Path]:
    """Find all .result files recursively in the given directory."""
    return list(base_dir.rglob("*.result"))


def parse_output_path(file_path: Path) -> Tuple[str, str, bool, str, int]:
    """
    Parse output path to extract metadata.
    Expected format: {output_dir}/{system}/{model}/[with_python/]{variation_name}_run_{run_index}.result
    """
    parts = file_path.parts
    
    # Find indices for system and model
    system_idx = -4 if "with_python" in parts else -3
    model_idx = -3 if "with_python" in parts else -2
    
    system = parts[system_idx]
    model = parts[model_idx]
    with_python = "with_python" in parts
    
    # Extract variation name and run index from filename
    filename = file_path.stem  # removes .result
    variation_name, run_part = filename.rsplit('_run_', 1)
    run_index = int(run_part)
    
    return system, model, with_python, variation_name, run_index


def evaluate_directory(base_dir: Path, config: InputConfig, config_path: str, evaluator_func) -> List[EvaluationResult]:
    """Evaluate all result files in the directory."""
    results = []
    result_files = find_result_files(base_dir)
    
    # Create mapping of variation names to ground truth paths
    ground_truth_paths = {}
    if config.ground_truth_path:
        ground_truth_paths['default'] = config.ground_truth_path
    if config.variations:
        for variation in config.variations:
            ground_truth_paths[variation.name] = variation.ground_truth_path
    
    for file_path in result_files:
        try:
            # Parse path to get metadata
            system, model, with_python, variation, run = parse_output_path(file_path)
            
            # Get ground truth path from config
            if variation not in ground_truth_paths:
                print(f"Warning: No ground truth path found for variation {variation}")
                continue
                
            ground_truth_path = ground_truth_paths[variation]
            
            # Handle relative paths - assume relative to config directory
            if not os.path.isabs(ground_truth_path):
                config_dir = os.path.dirname(os.path.abspath(config_path))
                ground_truth_path = os.path.join(config_dir, ground_truth_path)
            
            if not os.path.exists(ground_truth_path):
                print(f"Warning: Ground truth file not found: {ground_truth_path}")
                continue
                
            # Evaluate
            score = evaluator_func(ground_truth_path, str(file_path))
            print(f"{str(file_path)},{score}")
            
            # Store result
            result = EvaluationResult(
                system=system,
                model=model,
                variation=variation,
                run=run,
                score=score,
                with_python=with_python
            )
            results.append(result)
            
        except Exception as e:
            print(f"Error processing {file_path}: {str(e)}")
            continue
            
    return results


def save_results(results: List[EvaluationResult], output_path: Path):
    import csv
    
    # Define the fieldnames based on the dataclass fields
    fieldnames = ['system', 'model', 'variation', 'run', 'score', 'with_python']
    
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        # Write each result as a row
        for r in results:
            writer.writerow({
                'system': r.system,
                'model': r.model,
                'variation': r.variation,
                'run': r.run,
                'score': r.score,
                'with_python': r.with_python
            })

    print(f"\nDetailed results saved to: {output_path}")

def main():
    parser = argparse.ArgumentParser(description='Evaluate results against ground truth')
    parser.add_argument('input_config', type=str, help='Path to input config YAML file')
    parser.add_argument('output_dir', type=str, help='Base output directory containing results')
    parser.add_argument('evaluator_module', type=str, help='Python module containing evaluate_score function')
    parser.add_argument('--results-file', type=str, default='evaluation-results.csv',
                       help='Path to save summary statistics (default: evaluation_summary.csv)')
    
    args = parser.parse_args()
    
    try:
        # Load config
        input_config = read_input_config(args.input_config)
        
        # Load evaluator module
        spec = importlib.util.spec_from_file_location("evaluator", args.evaluator_module)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load module: {args.evaluator_module}")
        
        evaluator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(evaluator)
        
        if not hasattr(evaluator, 'evaluate_score'):
            raise ImportError("Module does not contain evaluate_score function")
        
        # Process directory
        base_dir = Path(args.output_dir)
        results = evaluate_directory(base_dir, input_config, args.input_config, evaluator.evaluate_score)
        
        save_results(results, Path(args.results_file))
        
        
    except Exception as e:
        print(traceback.format_exc())
        print(f"Error: {str(e)}")
        return 1
        
    return 0

if __name__ == "__main__":
    exit(main())