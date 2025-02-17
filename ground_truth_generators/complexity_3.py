from datetime import datetime, timezone
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
    # Get current time in UTC
    current_time = datetime.now(timezone.utc)

    # Get last N open tickets
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
    
    if project_ids:
        project_ids_str = "'" + "','".join(project_ids) + "'"
        sql = f"""
        SELECT 
            pc.project_id,
            FIRST_VALUE(p.name) OVER (
                PARTITION BY pc.project_id 
                ORDER BY pc.created_at DESC
            ) as plan_name
        FROM app.project_plan_changelogs pc
        LEFT JOIN app.plans p ON p.id = pc.plan_id
        WHERE pc.project_id IN ({project_ids_str})
        """
        project_plans = executor.run_sql(sql)
        plan_map = {p['project_id']: p['plan_name'] for p in project_plans}
    else:
        plan_map = {}

    # Get ticket categories from artifact
    ticket_categories = executor.get_artifact('ticket_category')
    ticket_category_dict = {t['id']: t['category'] for t in ticket_categories}

    # Define category priority (lower number = higher priority)
    category_priority = {
        'Downtime': 1,
        'Reliability': 2,
        'Performance': 3,
        'Bug': 4,
        'Feature request': 5,
        'How-to': 6
    }

    prioritized_tickets = []
    for ticket, project_id in zip(tickets, project_ids):
        # Parse created_at as UTC datetime
        created_at_str = ticket['created_at']
        # Remove timezone suffix if present and add UTC
        created_at_str = created_at_str.replace('Z', '+00:00')
        if '+' not in created_at_str and '-' not in created_at_str[-6:]:
            created_at_str += '+00:00'
        created_at = datetime.fromisoformat(created_at_str)
        
        # Calculate time since creation
        time_since_creation = (current_time - created_at).total_seconds() / 3600  # in hours
        
        # Get ticket category
        category = ticket_category_dict.get(str(ticket['id']), 'unknown')
        plan = plan_map.get(project_id, 'unknown')
        
        # Create priority tuple
        # First element: 1 if advanced plan + (downtime/reliability), 2 otherwise
        is_high_priority = (plan == 'advanced' and category in ['Downtime', 'Reliability'])
        priority_1 = 1 if is_high_priority else 2
        
        # Second element: category priority
        priority_2 = category_priority.get(category, 7)  # 7 for unknown categories
        
        # Third element: negative time (so older tickets get higher priority)
        priority_3 = -time_since_creation
        
        prioritized_tickets.append({
            'ticket_id': ticket['id'],
            'subject': ticket['subject'],
            'project_id': project_id,
            'time_since_creation_hours': round(time_since_creation, 1),
            'category': category,
            'plan': plan,
            'priority_tuple': (priority_1, priority_2, priority_3)
        })

    # Sort by priority tuple
    prioritized_tickets.sort(key=lambda x: x['priority_tuple'])

    # Take top k and remove priority tuple from final output
    final_tickets = []
    for ticket in prioritized_tickets[:top_k_tickets]:
        ticket_data = ticket.copy()
        del ticket_data['priority_tuple']
        final_tickets.append(ticket_data)

    # Store results
    executor.store_artifact(
        'prioritized_tickets',
        f'Top {top_k_tickets} Priority Support Tickets',
        'table',
        final_tickets
    )

    return final_tickets

tickets = prioritize_tickets(n_last_tickets=10, top_k_tickets=3)  # Custom numbers