import traceback
import numpy as np
from scipy.stats import kendalltau
from sklearn.metrics import ndcg_score
import json


def evaluate_ticket_prioritization(
    expected_list, actual_list, missing_penalty=0.2, extra_penalty=0.2
):
    """
    Evaluates the accuracy of a ticket prioritization system using Kendall's Tau correlation
    with penalties for missing or extra tickets.

    Parameters:
    -----------
    expected_list : list
        The ground truth list of ticket IDs in priority order
    actual_list : list
        The system-generated list of ticket IDs in priority order
    missing_penalty : float, optional (default=0.2)
        Penalty per missing ticket (as a fraction of total score)
    extra_penalty : float, optional (default=0.2)
        Penalty per extra/unknown ticket (as a fraction of total score)

    Returns:
    --------
    float
        Accuracy score between 0 and 1
    """
    # Create sets for faster lookup
    expected_set = set(expected_list)
    actual_set = set(actual_list)

    # Find missing and extra tickets
    missing_tickets = expected_set - actual_set
    extra_tickets = actual_set - expected_set

    # Calculate penalties
    missing_penalty_total = len(missing_tickets) * missing_penalty
    extra_penalty_total = len(extra_tickets) * extra_penalty

    # Find common tickets to calculate Kendall's Tau
    common_tickets = expected_set.intersection(actual_set)

    # If there are no common tickets, return 0
    if not common_tickets:
        return 0.0

    # Create indexed dictionaries for ranking
    expected_rank = {
        ticket_id: rank
        for rank, ticket_id in enumerate(expected_list)
        if ticket_id in common_tickets
    }
    actual_rank = {
        ticket_id: rank
        for rank, ticket_id in enumerate(actual_list)
        if ticket_id in common_tickets
    }

    # Get ordered lists of rankings for common tickets
    common_tickets_list = list(common_tickets)
    expected_ranks = [expected_rank[ticket] for ticket in common_tickets_list]
    actual_ranks = [actual_rank[ticket] for ticket in common_tickets_list]

    # Calculate Kendall's Tau correlation
    tau, _ = kendalltau(expected_ranks, actual_ranks)

    # Convert to a more meaningful 0-1 scale
    # A tau of 0 (no correlation) should map closer to 0 accuracy
    # We'll use max(0, tau) to treat negative correlations as 0
    # Then scale the positive range [0,1] to represent accuracy
    tau_normalized = max(0, tau)

    # Apply penalties (ensuring the result stays between 0 and 1)
    final_score = max(
        0.0, min(1.0, tau_normalized - missing_penalty_total - extra_penalty_total)
    )

    if final_score > 0.999:
        final_score = 1.0

    return final_score


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
        try:
            test_result_json = json.loads(test_result)
            if not isinstance(test_result_json, list):
                return 0
        except json.JSONDecodeError:
            return 0

        ground_truth_values = [next(iter(item.values())) for item in ground_truth_json]
        test_values = [next(iter(item.values())) for item in test_result_json]

        return evaluate_ticket_prioritization(ground_truth_values, test_values)
    except Exception as e:
        print(traceback.format_exc())
        print(f"Error during processing: {e}")
        raise e
