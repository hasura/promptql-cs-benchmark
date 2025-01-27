import datetime
import re

def prioritize_tickets(n_last_tickets=5, top_k_tickets=5):
    """
    Prioritize support tickets based on specified parameters.
    
    Args:
        n_last_tickets (int): Number of last open tickets to analyze
        top_k_tickets (int): Number of top priority tickets to return
        
    Returns:
        list: Top-k prioritized tickets
    """
    # Get the last N open tickets
    sql = f"""
    SELECT 
        id,
        subject,
        description,
        created_at,
        status
    FROM app.support_ticket 
    WHERE status = 'open'
    ORDER BY created_at DESC
    LIMIT {n_last_tickets}
    """
    open_tickets = executor.run_sql(sql)
    
    # Get ticket categories from artifact
    ticket_categories = executor.get_artifact('ticket_category')
    category_map = {tc['id']: tc['category'] for tc in ticket_categories}
    
    # Current time for calculating time since creation
    current_time = datetime.datetime.strptime('2025-01-22 08:03:01', '%Y-%m-%d %H:%M:%S')
    
    # Process each ticket
    prioritized_tickets = []
    for ticket in open_tickets:
        # Extract project_id from description using regex
        project_id = None
        if ticket['description']:
            project_id_match = re.search(r'project[_\s-]?id[\s:]+([a-zA-Z0-9-]+)', ticket["description"], re.IGNORECASE)
            project_id = project_id_match.group(1) if project_id_match else None
        
        # Calculate time since creation
        created_at = datetime.datetime.strptime(ticket['created_at'].split('.')[0], 
                                              '%Y-%m-%dT%H:%M:%S')
        time_since_creation = current_time - created_at
        
        # Get category
        category = category_map.get(str(ticket['id']), 'Uncategorized')
        
        prioritized_tickets.append({
            'ticket_id': ticket['id'],
            'subject': ticket['subject'],
            'project_id': project_id,
            'time_since_creation': str(time_since_creation),
            'category': category,
            'created_at': ticket['created_at']
        })
    
    # Sort by creation time (oldest first)
    prioritized_tickets.sort(key=lambda x: x['created_at'])
    
    # Limit to top-k tickets
    prioritized_tickets = prioritized_tickets[:top_k_tickets]
    
    # Store results
    executor.store_artifact(
        identifier='prioritized_tickets',
        title=f'Top {top_k_tickets} Priority Support Tickets',
        artifact_type='table',
        data=prioritized_tickets
    )
    
    return prioritized_tickets

# Example usage
prioritized_tickets = prioritize_tickets(n_last_tickets=5, top_k_tickets=5)