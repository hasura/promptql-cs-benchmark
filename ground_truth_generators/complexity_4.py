import datetime
from datetime import timezone
from typing import List, Dict
import re

def prioritize_tickets(
    n_last_tickets: int = 5,
    top_k_tickets: int = 5
) -> List[Dict]:
    """
    Prioritize support tickets based on specified parameters, using LLM extraction
    for project IDs.
    
    Args:
        n_last_tickets (int): Number of last open tickets to analyze
        top_k_tickets (int): Number of top priority tickets to return
    
    Returns:
        list: Top-k prioritized tickets
    """
    # Get the last N open tickets
    sql = f"""
    SELECT 
        t.id,
        t.subject,
        t.description,
        t.created_at,
        t.status
    FROM app.support_ticket t
    WHERE t.status = 'open'
    ORDER BY t.created_at DESC
    LIMIT {n_last_tickets}
    """
    tickets = executor.run_sql(sql)

    # Extract project_ids using regex - get last match if multiple exist
    project_id_pattern = r'Project ID: ([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
    
    project_ids = []
    for ticket in tickets:
        matches = list(re.finditer(project_id_pattern, ticket['description']))
        project_id = matches[-1].group(1) if matches else None
        project_ids.append(project_id)

    # Get ticket categories from artifact
    ticket_categories = executor.get_artifact('ticket_category')
    category_map = {tc['id']: tc['category'] for tc in ticket_categories}

    # Get project plans - Modified to get most recent plan for each project
    if project_ids:
        project_ids_str = "'" + "','".join(project_ids) + "'"
        sql = f"""
        WITH RankedPlans AS (
            SELECT 
                pc.project_id,
                pl.name as plan_name,
                ROW_NUMBER() OVER (PARTITION BY pc.project_id ORDER BY pc.created_at DESC) as rn
            FROM app.project_plan_changelogs pc
            JOIN app.plans pl ON pc.plan_id = pl.id
            WHERE pc.project_id IN ({project_ids_str})
        )
        SELECT project_id, plan_name
        FROM RankedPlans
        WHERE rn = 1
        """
        project_plans = executor.run_sql(sql)
        plan_map = {p['project_id']: p['plan_name'].lower() for p in project_plans}
    else:
        plan_map = {}

    # Define category priority
    category_priority = {
        'Downtime': 6,
        'Reliability': 5,
        'Performance': 4,
        'Bug': 3,
        'Feature request': 2,
        'How-to': 1
    }

    # Calculate priority tuples and create final data
    current_time = datetime.datetime.now(timezone.utc)
    prioritized_tickets = []

    for ticket, project_id in zip(tickets, project_ids):
        category = category_map.get(str(ticket['id']), 'Unknown')
        plan = plan_map.get(project_id, 'free')  # Default to 'free' instead of 'Unknown'
        
        # Parse created_at with robust handling of different formats
        created_at_str = ticket['created_at']
        try:
            if '.' in created_at_str:
                created_at = datetime.datetime.strptime(created_at_str, '%Y-%m-%dT%H:%M:%S.%f')
            else:
                created_at = datetime.datetime.strptime(created_at_str, '%Y-%m-%dT%H:%M:%S')
            created_at = created_at.replace(tzinfo=timezone.utc)
        except ValueError as e:
            executor.print(f"Error parsing date {created_at_str}: {e}")
            created_at = current_time  # fallback to current time if parsing fails
        
        hours_since_creation = (current_time - created_at).total_seconds() / 3600
        
        # Determine priority group (Rule 1, 2, and 3)
        is_critical_issue = category in ['Downtime', 'Reliability']
        if is_critical_issue and plan == 'advanced':
            priority_group = 3
        elif is_critical_issue and plan == 'base':
            priority_group = 2
        else:
            priority_group = 1
        
        prioritized_tickets.append({
            'ticket_id': ticket['id'],
            'subject': ticket['subject'],
            'project_id': project_id,
            'hours_since_creation': round(hours_since_creation, 1),
            'category': category,
            'project_plan': plan,
            'priority_group': priority_group,
            'priority_explanation': (
                'Advanced plan with critical issue' if priority_group == 3 else
                'Base plan with critical issue' if priority_group == 2 else
                'Other issue'
            )
        })

    # Sort tickets by priority tuple (reverse=True for descending order)
    prioritized_tickets.sort(key=lambda x: (
        x['priority_group'],
        category_priority.get(x['category'], 0),
        x['hours_since_creation']
    ), reverse=True)

    # Take only top-k tickets
    prioritized_tickets = prioritized_tickets[:top_k_tickets]

    # Store prioritized tickets
    executor.store_artifact(
        'prioritized_tickets',
        f'Top {top_k_tickets} Priority Support Tickets',
        'table',
        prioritized_tickets
    )

    return prioritized_tickets

# Example usage
tickets = prioritize_tickets(n_last_tickets=10, top_k_tickets=3)  # Custom numbers