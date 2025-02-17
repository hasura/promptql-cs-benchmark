#!/usr/bin/env python3

import json
import traceback


def evaluate_score(ground_truth: str, test_result: str) -> float:
    """
    Dummy evaluation function that always returns 0.5
    
    Args:
        ground_truth (str): Path to the ground truth file
        test_result (str): Path to the test result file
    
    Returns:
        float: Always returns 0.5
    """
    try:
        ground_truth_json = json.loads(ground_truth)
        test_result_json = json.loads(test_result)
        if ground_truth_json == test_result_json:
            score = 1
        else:
            score = 0
        return score
    except Exception as e:
        print(traceback.format_exc())
        print(f"Error during processing: {e}")
        raise e
