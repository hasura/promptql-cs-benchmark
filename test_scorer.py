#!/usr/bin/env python3

def evaluate_score(ground_truth: str, test_result: str) -> float:
    """
    Dummy evaluation function that always returns 0.5
    
    Args:
        ground_truth (str): Path to the ground truth file
        test_result (str): Path to the test result file
    
    Returns:
        float: Always returns 0.5
    """
    if ground_truth == test_result:
        score = 1
    else:
        score = 0
    return score
