import requests
from datetime import datetime, date, timedelta
from collections import defaultdict
import itertools

# [GraphQL templates remain the same...]
GRAPHQL_REQUEST_TEMPLATE = """
query FindUsersWithEqualErrorRates($_gte: date = "{start_date}", $_lte: date = "{end_date}") {{
  projects(
    where: {{error_rate_dailies: {{_and: [{{error_rate: {{_is_null: false}}}}, {{date: {{_gte: $_gte, _lte: $_lte}}}}]}}}}
  ) {{
    id
    error_rate_dailies_aggregate(
      filter_input: {{where: {{date: {{_gte: $_gte, _lte: $_lte}}}}}}
    ) {{
      error_rate {{
        avg
      }}
    }}
    user {{
      email
    }}
  }}
}}
"""

SUPPORT_TICKETS_TEMPLATE = """
query GetUserTickets {{
  support_ticket(
    where: {{support_user_by_requester_id: {{email: {{_eq: "{email}"}}}}}}
  ) {{
    id
  }}
}}
"""

GRAPHQL_URL = "http://localhost:3280/graphql"

def get_support_tickets(email):
    query = SUPPORT_TICKETS_TEMPLATE.format(email=email)
    response = requests.post(
        GRAPHQL_URL,
        json={'query': query}
    )
    if response.status_code == 200:
        data = response.json()
        tickets = data.get('data', {}).get('support_ticket', [])
        return {
            'count': len(tickets),
            'ticket_ids': [ticket['id'] for ticket in tickets]
        }
    return {'count': 0, 'ticket_ids': []}

def find_highest_equal_error_rates(start_date, end_date, min_projects=2, verbose=False):
    """
    Find projects with equal error rates that are also the highest error rates
    within the given date range.
    """
    current_query = GRAPHQL_REQUEST_TEMPLATE.format(
        start_date=start_date,
        end_date=end_date
    )
    
    response = requests.post(
        GRAPHQL_URL,
        json={'query': current_query}
    )
    
    if response.status_code != 200:
        print(f"Request failed with status code: {response.status_code}")
        print(f"Error message: {response.text}")
        return None

    projects = response.json()
    all_projects = projects["data"]["projects"]
    
    if verbose:
        print(f"Found {len(all_projects)} projects in this period")
    
    if not all_projects:
        return {}

    # Group projects by their error rates
    error_rates = defaultdict(list)
    highest_rate = 0
    for project in all_projects:
        error_rate = project["error_rate_dailies_aggregate"]["error_rate"]["avg"]
        if error_rate is not None and error_rate > 0:  # Exclude zero error rates
            # Round to 6 decimal places to handle floating point comparison
            rounded_rate = round(error_rate, 6)
            error_rates[rounded_rate].append({
                "id": project["id"],
                "email": project["user"]["email"],
                "error_rate": error_rate
            })
            highest_rate = max(highest_rate, rounded_rate)
    
    if verbose:
        # print(f"Found {len(error_rates)} unique non-zero error rates")
        if error_rates:
            # Print top 3 error rates and their project counts
            sorted_rates = sorted(error_rates.items(), key=lambda x: x[0], reverse=True)[:3]
            for rate, projects in sorted_rates:
                print(f"  Rate {rate}: {len(projects)} projects")
        else:
            print("  No non-zero error rates found in this period")

    # Only return groups with the highest error rate AND at least min_projects
    if highest_rate in error_rates and len(error_rates[highest_rate]) >= min_projects:
        return {highest_rate: error_rates[highest_rate]}
    return {}

def search_until_match(start_year=2024, search_backwards=False, verbose=False, count=0):
    """
    Search through different date ranges until finding matching highest error rates.
    """
    window_sizes = [1, 2, 3, 4, 5, 7, 10, 14, 21, 30]
    
    if search_backwards:
        start_date = datetime(start_year, 12, 31)
        end_year = datetime(start_year, 1, 1)
    else:
        start_date = datetime(start_year, 1, 1)
        end_year = datetime(start_year, 12, 31)
    
    for window_size in window_sizes:
        print(f"\nTrying {window_size}-day windows...")
        
        step_size = 1  # Move just one day at a time
        current_start = start_date
        
        while (current_start <= end_year) if not search_backwards else (current_start >= end_year):
            current_end = current_start + timedelta(days=window_size) if not search_backwards else current_start
            current_start_actual = current_start if not search_backwards else current_start - timedelta(days=window_size)
            
            # Ensure dates are within year bounds
            if not search_backwards:
                current_end = min(current_end, end_year)
            else:
                current_start_actual = max(current_start_actual, end_year)
            
            start_str = current_start_actual.strftime("%Y-%m-%d")
            end_str = current_end.strftime("%Y-%m-%d")
            
            if verbose:
                print(f"\nAnalyzing period: {start_str} to {end_str}")
            
            matching_groups = find_highest_equal_error_rates(start_str, end_str, min_projects=2, verbose=verbose)
            
            if matching_groups:
                count += 1
                print("\n=== FOUND MATCHING HIGHEST ERROR RATES ===")
                print(f"Time window: {window_size} days")
                print(f"Period: {start_str} to {end_str}")
                
                for error_rate, projects in matching_groups.items():
                    print(f"\nHighest error rate: {error_rate}")
                    print(f"Number of projects with this rate: {len(projects)}")
                    print("\nProjects:")
                    for project in projects:
                        print(f"\nProject ID: {project['id']}")
                        print(f"User email: {project['email']}")
                        
                        ticket_info = get_support_tickets(project['email'])
                        print(f"Support tickets:")
                        print(f"  Count: {ticket_info['count']}")
                        print(f"  Ticket IDs: {ticket_info['ticket_ids']}")
                    print("=" * 50)
                if count > 2:
                    return True
            
            # Move to next period
            if not search_backwards:
                current_start += timedelta(days=step_size)
            else:
                current_start -= timedelta(days=step_size)
    
    print("\nNo matching highest error rates found after trying all date ranges.")
    return False

if __name__ == "__main__":
    search_until_match(start_year=2023, verbose=False)