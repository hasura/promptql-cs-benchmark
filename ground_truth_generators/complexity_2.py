import datetime
from datetime import timezone
from typing import Dict, List

def prioritize_tickets(
    n_last_tickets: int = 5,
    top_k_tickets: int = 5
) -> List[dict]:
    """
    Prioritize support tickets based on specified parameters.
    
    Args:
        n_last_tickets (int): Number of last open tickets to analyze
        top_k_tickets (int): Number of top priority tickets to return
    
    Returns:
        list: Top-k prioritized tickets
    """
    # Fixed category priority mapping (lower number = higher priority)
    category_priority = {
        'Downtime': 1,
        'Reliability': 2,
        'Performance': 3,
        'Bug': 4,
        'Feature request': 5,
        'How-to': 6
    }

    # Get all valid project IDs first
    sql = """
    SELECT id FROM app.projects
    """
    valid_projects = executor.run_sql(sql)
    valid_project_ids = {p['id'] for p in valid_projects}

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
    open_tickets = executor.run_sql(sql)

    # Get ticket categories from artifact
    ticket_categories = executor.get_artifact('ticket_category')
    ticket_category_map = {t['id']: t['category'] for t in ticket_categories}

    # Process each ticket
    processed_tickets = []
    current_time = datetime.datetime.now(timezone.utc)
    
    for ticket in open_tickets:
        # Extract project_id from description
        description = ticket['description'] or ''
        
        # Look for any valid project ID in the description
        found_project_id = None
        for project_id in valid_project_ids:
            if project_id in description:
                found_project_id = project_id
                break
        
        if found_project_id:
            # Get most recent plan for the project
            sql = f"""
            SELECT p.name as plan_name
            FROM app.project_plan_changelogs pc
            JOIN app.plans p ON p.id = pc.plan_id
            WHERE pc.project_id = '{found_project_id}'
            ORDER BY pc.created_at DESC
            LIMIT 1
            """
            plan_result = executor.run_sql(sql)
            plan = plan_result[0]['plan_name'] if plan_result else 'Unknown'
            
            # Calculate time since creation with proper timezone handling
            created_at_str = ticket['created_at']
            # If the timestamp doesn't have timezone info, assume UTC
            if created_at_str.endswith('Z'):
                created_at_str = created_at_str[:-1] + '+00:00'
            elif '+' not in created_at_str and '-' not in created_at_str[-6:]:
                created_at_str = created_at_str + '+00:00'
                
            created_at = datetime.datetime.fromisoformat(created_at_str)
            # Ensure created_at is in UTC
            if created_at.tzinfo is not None:
                created_at = created_at.astimezone(timezone.utc)
            else:
                created_at = created_at.replace(tzinfo=timezone.utc)
                
            time_since_creation = current_time - created_at
            
            # Get category
            category = ticket_category_map.get(str(ticket['id']), 'Unknown')
            
            # Create priority tuple
            # (category_priority, -seconds_since_creation)
            priority = (
                category_priority.get(category, 999),  # Unknown categories get lowest priority
                -int(time_since_creation.total_seconds())
            )
            
            processed_tickets.append({
                'ticket_id': ticket['id'],
                'subject': ticket['subject'],
                'project_id': found_project_id,
                'category': category,
                'plan': plan,
                'time_since_creation': str(time_since_creation).split('.')[0],  # Remove microseconds
                'priority_tuple': priority
            })

    # Sort by priority tuple and take top k
    sorted_tickets = sorted(processed_tickets, key=lambda x: x['priority_tuple'])[:top_k_tickets]
    
    # Remove priority tuple from final output
    final_tickets = [{k: v for k, v in ticket.items() if k != 'priority_tuple'} 
                    for ticket in sorted_tickets]

    # Store results
    executor.store_artifact(
        'prioritized_tickets',
        f'Top {top_k_tickets} Priority Support Tickets',
        'table',
        final_tickets
    )

    # Print debug info
    executor.print(f"Found {len(open_tickets)} open tickets")
    executor.print(f"Successfully processed {len(processed_tickets)} tickets with valid project IDs")

    return final_tickets

# Example usage
tickets = prioritize_tickets(n_last_tickets=10, top_k_tickets=3)  # Custom numbers