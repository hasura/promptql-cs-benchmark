import requests
from datetime import datetime, date

# Base GraphQL query with placeholder dates - note the double curly braces for escaping
GRAPHQL_REQUEST_TEMPLATE = """
query FindUserWithHighestErrorRate($_gte: date = "{start_date}", $_lte: date = "{end_date}") {{
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

# Support tickets query template
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

# Month ranges for 2024
month_ranges = [
    ("2024-01-01", "2024-01-31"),
    ("2024-02-01", "2024-02-29"),  # 2024 is a leap year
    ("2024-03-01", "2024-03-31"),
    ("2024-04-01", "2024-04-30"),
    ("2024-05-01", "2024-05-31"),
    ("2024-06-01", "2024-06-30"),
    ("2024-07-01", "2024-07-31"),
    ("2024-08-01", "2024-08-31"),
    ("2024-09-01", "2024-09-30"),
    ("2024-10-01", "2024-10-31"),
    ("2024-11-01", "2024-11-30"),
    ("2024-12-01", "2024-12-31"),
    ("2024-03-14", "2024-03-16"),
    ("2024-11-01", "2024-11-15"),
    ("2023-10-15", "2023-10-18")
]

# Loop through each month
for start_date, end_date in month_ranges:
    print(f"\nAnalyzing period: {start_date} to {end_date}")
    
    # Format the query with the current month's dates
    current_query = GRAPHQL_REQUEST_TEMPLATE.format(
        start_date=start_date,
        end_date=end_date
    )
    
    # Send the GraphQL request
    response = requests.post(
        GRAPHQL_URL,
        json={'query': current_query}
    )
    
    # Check if the request was successful
    if response.status_code == 200:
        # Parse the response
        projects = response.json()
        
        highest_errors = 0
        highest_errors_id = []
        highest_errors_emails = []

        for p in projects["data"]["projects"]:
            if p["error_rate_dailies_aggregate"]["error_rate"]["avg"] > highest_errors:
                highest_errors = p["error_rate_dailies_aggregate"]["error_rate"]["avg"]
                highest_errors_id = [p["id"]]
                highest_errors_emails = [p["user"]["email"]]
            elif p["error_rate_dailies_aggregate"]["error_rate"]["avg"] == highest_errors:
                highest_errors_id.append(p["id"])
                highest_errors_emails.append(p["user"]["email"])

        print(f"Highest error rate: {highest_errors}")
        print(f"Project IDs: {highest_errors_id}")
        print(f"User emails: {highest_errors_emails}")
        
        # Get support tickets for each user with highest error rate
        for email in highest_errors_emails:
            ticket_info = get_support_tickets(email)
            print(f"Support tickets for {email}:")
            print(f"  Count: {ticket_info['count']}")
            print(f"  Ticket IDs: {ticket_info['ticket_ids']}")
    else:
        print(f"Request failed with status code: {response.status_code}")
        print(f"Error message: {response.text}")