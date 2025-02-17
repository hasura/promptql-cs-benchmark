import requests
import json
import re
import argparse
import os
from typing import Any

def execute_program(filename: str, n_last_tickets: int, top_k_tickets: int) -> Any:
    """
    Load a file containing PromptQL code and execute it with parameters.
    
    Args:
        filename: Name of the file containing the code
        n_last_tickets: Number of last tickets to analyze
        top_k_tickets: Number of top priority tickets to return
    
    Returns:
        API response data
    """
    # Check for required environment variables
    promptql_api_key = os.getenv('PROMPTQL_SECRET_KEY')
    llm_api_key = os.getenv('ANTHROPIC_API_KEY')
    
    if not promptql_api_key:
        raise Exception("PROMPTQL_SECRET_KEY environment variable is not set")
    if not llm_api_key:
        raise Exception("ANTHROPIC_API_KEY environment variable is not set")
    
    try:
        with open(filename, 'r') as file:
            code = file.read()
    except FileNotFoundError:
        raise Exception(f"File {filename} not found")
    
    code = re.sub(
        r'tickets = prioritize_tickets\(.*?\)',
        f'tickets = prioritize_tickets(n_last_tickets={n_last_tickets}, top_k_tickets={top_k_tickets})',
        code
    )
    
    url = "https://api.promptql.pro.hasura.io/execute_program"
    headers = {
        "Content-Type": "application/json"
    }
    
    payload = {
        "code": code,
        "promptql_api_key": promptql_api_key,
        "ai_primitives_llm": {
            "provider": "anthropic",
            "api_key": llm_api_key
        },
        "ddn": {
            "url": "https://destined-buck-3238.ddn.hasura.app/v1/sql",
            "headers": {}
        },
        "artifacts": [
            {
                "identifier": "ticket_category",
                "title": "Support Ticket Categories",
                "artifact_type": "table",
                "data": [
                    {"id": "139", "category": "Downtime"},
                    {"id": "143", "category": "Downtime"},
                    {"id": "144", "category": "Downtime"},
                    {"id": "150", "category": "Downtime"},
                    {"id": "166", "category": "Feature request"},
                    {"id": "169", "category": "Performance"},
                    {"id": "175", "category": "Performance"},
                    {"id": "178", "category": "Downtime"},
                    {"id": "180", "category": "Downtime"},
                    {"id": "182", "category": "Performance"},
                    {"id": "186", "category": "Reliability"},
                    {"id": "187", "category": "Reliability"},
                    {"id": "188", "category": "Reliability"},
                    {"id": "190", "category": "Reliability"},
                    {"id": "193", "category": "Downtime"},
                    {"id": "195", "category": "Reliability"},
                    {"id": "197", "category": "Downtime"},
                    {"id": "201", "category": "Downtime"},
                    {"id": "203", "category": "Performance"},
                    {"id": "205", "category": "Downtime"},
                    {"id": "209", "category": "Downtime"},
                    {"id": "214", "category": "Performance"},
                    {"id": "215", "category": "Reliability"},
                    {"id": "224", "category": "Downtime"},
                    {"id": "228", "category": "Downtime"},
                    {"id": "230", "category": "Performance"},
                    {"id": "237", "category": "Downtime"},
                    {"id": "246", "category": "Downtime"},
                    {"id": "247", "category": "Downtime"},
                    {"id": "250", "category": "Performance"},
                    {"id": "251", "category": "Performance"},
                    {"id": "259", "category": "Reliability"},
                    {"id": "261", "category": "Performance"},
                    {"id": "264", "category": "Downtime"},
                    {"id": "265", "category": "Performance"},
                    {"id": "267", "category": "Reliability"},
                    {"id": "275", "category": "Performance"},
                    {"id": "276", "category": "Downtime"},
                    {"id": "277", "category": "Reliability"}
                ]
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"API request failed: {str(e)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Execute PromptQL program with parameters')
    parser.add_argument('filename', type=str, help='Path to the file containing the code')
    parser.add_argument('--n_last_tickets', type=int, default=10, 
                        help='Number of last tickets to analyze (default: 5)')
    parser.add_argument('--top_k_tickets', type=int, default=3,
                        help='Number of top priority tickets to return (default: 5)')
    
    args = parser.parse_args()
    
    try:
        result = execute_program(
            args.filename,
            args.n_last_tickets,
            args.top_k_tickets
        )
        print(json.dumps(result, indent=2))
    except Exception as e:
        print("Error:", str(e))