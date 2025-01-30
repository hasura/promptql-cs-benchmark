import datetime
from datetime import timezone
from typing import List, Dict
import re

def prioritize_tickets(
    n_last_tickets: int = 5,
    top_k_tickets: int = 5
) -> List[Dict]:
    """
    Prioritize support tickets based on specified parameters.
    
    Args:
        n_last_tickets (int): Number of last open tickets to analyze
        top_k_tickets (int): Number of top priority tickets to return
    
    Returns:
        list: Top-k prioritized tickets
    """
    current_time = datetime.datetime.now(timezone.utc)
    
    # Get the last N open tickets
    sql = f"""
    SELECT 
        t.id as ticket_id,
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

    # Get ticket categories from artifact
    ticket_categories = executor.get_artifact('ticket_category')
    category_map = {t['id']: t['category'] for t in ticket_categories}

    # Define category priority
    category_priority = {
        'Downtime': 1,
        'Reliability': 2,
        'Performance': 3,
        'Bug': 4,
        'Feature request': 5,
        'How-to': 6
    }

    # Extract project_ids using regex - get last match if multiple exist
    project_id_pattern = r'Project ID: ([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
    
    project_ids = []
    for ticket in tickets:
        matches = list(re.finditer(project_id_pattern, ticket['description']))
        project_id = matches[-1].group(1) if matches else None
        project_ids.append(project_id)

    prioritized_tickets = []
    for ticket, project_id in zip(tickets, project_ids):
        
        if not project_id:
            executor.print(f"Could not find project_id for ticket {ticket['ticket_id']}")
            continue

        # Get project's current plan
        sql = f"""
        SELECT p.name as plan_name
        FROM app.project_plan_changelogs pc
        JOIN app.plans p ON p.id = pc.plan_id
        WHERE pc.project_id = '{project_id}'
        ORDER BY pc.created_at DESC
        LIMIT 1
        """
        plan_results = executor.run_sql(sql)
        plan = plan_results[0]['plan_name'].lower() if plan_results else None

        # Calculate time since creation with proper timezone handling
        created_at_str = ticket['created_at']
        if not created_at_str.endswith('Z') and '+' not in created_at_str:
            created_at_str += 'Z'
        created_at = datetime.datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
        time_since_creation = current_time - created_at

        # Get category
        category = category_map.get(str(ticket['ticket_id']))
        
        # Determine priority level based on the rules
        if category in ['Downtime', 'Reliability']:
            if plan == 'advanced':
                priority_level = 1
            elif plan == 'base':
                priority_level = 2
            elif category == 'Downtime':  # Free plan + Downtime
                priority_level = 3
            else:  # Free plan + Reliability falls to level 4
                priority_level = 4
        else:
            priority_level = 4

        # Create priority tuple
        priority_tuple = (
            priority_level,
            category_priority.get(category, 7),
            -time_since_creation.total_seconds()
        )

        prioritized_tickets.append({
            'ticket_id': ticket['ticket_id'],
            'subject': ticket['subject'],
            'project_id': project_id,
            'time_since_creation': str(time_since_creation).split('.')[0],
            'category': category,
            'plan': plan or 'free',
            'priority_tuple': priority_tuple
        })

    # Sort by priority tuple and take top k
    prioritized_tickets.sort(key=lambda x: x['priority_tuple'])
    top_k_tickets_list = prioritized_tickets[:top_k_tickets]

    # Remove priority tuple before storing in artifact
    for ticket in top_k_tickets_list:
        del ticket['priority_tuple']

    executor.store_artifact(
        'prioritized_tickets',
        f'Top {top_k_tickets} Priority Support Tickets',
        'table',
        top_k_tickets_list
    )

    return top_k_tickets_list

tickets = prioritize_tickets(n_last_tickets=10, top_k_tickets=3)  # Custom numbers