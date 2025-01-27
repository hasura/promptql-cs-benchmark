import csv
import argparse
from datetime import datetime
from typing import List, Dict
from ground_truth_generator import execute_program

def extract_ticket_ids(result: Dict) -> List[int]:
    """Extract ticket IDs from the API response."""
    try:
        artifacts = result.get('modified_artifacts', [])
        for artifact in artifacts:
            if artifact.get('identifier') == 'prioritized_tickets':
                return [ticket['ticket_id'] for ticket in artifact.get('data', [])]
    except Exception as e:
        print(f"Error extracting ticket IDs: {str(e)}")
        return []
    return []

def parameter_sweep(input_file: str, output_file: str) -> None:
    """
    Perform parameter sweep and save results as CSV.
    
    Args:
        input_file: Path to the input PromptQL code file
        output_file: Path to save the results CSV file
    """
    # Initialize CSV file with headers using proper quoting
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(['top_k_tickets', 'n_last_tickets', 'ticket_ids'])
    
    total_combinations = (30 - 5 + 1) * (5 - 1 + 1)
    current_combination = 0
    
    try:
        for top_k in range(1, 6):  # 1 to 5 inclusive
            for n_last in range(5, 31):  # 5 to 30 inclusive
                current_combination += 1
                print(f"\nProcessing combination {current_combination}/{total_combinations}")
                print(f"Parameters: top_k_tickets={top_k}, n_last_tickets={n_last}")
                
                try:
                    # Execute the program with current parameters
                    result = execute_program(
                        filename=input_file,
                        n_last_tickets=n_last,
                        top_k_tickets=top_k
                    )
                    
                    # Extract ticket IDs and join them with commas
                    ticket_ids = extract_ticket_ids(result)
                    ticket_ids_str = ','.join(map(str, ticket_ids))
                    
                    # Save to CSV with proper quoting
                    with open(output_file, 'a', newline='') as f:
                        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
                        writer.writerow([
                            top_k,
                            n_last,
                            ticket_ids_str  # This will be automatically quoted if it contains commas
                        ])
                    
                    print(f"Ticket IDs: {ticket_ids_str}")
                    
                except Exception as e:
                    # Log error and write empty result to CSV
                    print(f"Error in combination: {str(e)}")
                    with open(output_file, 'a', newline='') as f:
                        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
                        writer.writerow([top_k, n_last, ''])
                
                print(f"Results appended to {output_file}")
                
    except KeyboardInterrupt:
        print("\nParameter sweep interrupted by user. Partial results saved.")
    
    print(f"\nParameter sweep completed. Results saved to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Perform parameter sweep over PromptQL program')
    parser.add_argument('--input_file', type=str, help='Path to the input file containing the PromptQL code')
    parser.add_argument('--output_file', type=str, help='Path to save the results CSV file')
    
    args = parser.parse_args()
    
    try:
        parameter_sweep(args.input_file, args.output_file)
    except Exception as e:
        print(f"Error during parameter sweep: {str(e)}")