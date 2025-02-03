from pprint import pprint
import random
import user_generator
import usage_generator
import plan_change_generator
import invoice_generator
import support_agent_generator
import support_ticket_generator
from typing import List, Dict
from datetime import datetime

import psycopg2
from psycopg2.extras import execute_values


PLANS = [
    {
        "name": "free",
        "created_at": "2021-11-21T08:28:23.277447+00:00",
        "updated_at": "2021-11-21T08:28:23.277447+00:00",
        "id": "2d41d1de-51fa-41ed-8acd-6ee63bcd316e"
    },
    {
        "name": "base",
        "created_at": "2021-11-18T10:19:30.419719+00:00",
        "updated_at": "2021-11-18T10:19:30.419719+00:00",
        "id": "307a87a8-9185-4711-8470-38cdb9b6b42a"
    },
    {
        "name": "advanced",
        "created_at": "2021-11-07T05:03:49.666391+00:00",
        "updated_at": "2021-11-07T05:03:49.666391+00:00",
        "id": "34a91812-c6ab-4e35-b011-7433bf68299d"
    },
    {
        "name": "base_trial",
        "created_at": "2021-12-25T14:11:53.120683+00:00",
        "updated_at": "2022-12-25T14:11:53.120683+00:00",
        "id": "ef8e3ee9-ee6c-41d0-b1a0-d01e39d49d4d"
    },
    {
        "name": "advanced_trial",
        "created_at": "2021-12-09T12:38:51.557607+00:00",
        "updated_at": "2021-12-09T12:38:51.557607+00:00",
        "id": "28058da3-610f-4d2f-94d8-10bf0a340d6b"
    }
]

def months_between(date1, date2):
    return (date1.year - date2.year) * 12 + (date1.month - date2.month)

def insert_plans(connection_params, plans: List[Dict]):

    conn = psycopg2.connect(**connection_params)
    cursor = conn.cursor()    
    
    """Insert plan data"""
    plan_values = [
        (plan['id'], plan['name'], plan['created_at'], plan['updated_at'])
        for plan in plans
    ]
    
    # Insert data
    execute_values(
        cursor,
        """
        INSERT INTO Plans (id, name, created_at, updated_at)
        VALUES %s
        ON CONFLICT (id) DO UPDATE 
        SET name = EXCLUDED.name,
            created_at = EXCLUDED.created_at,
            updated_at = EXCLUDED.updated_at
        """,
        plan_values,
        template="(%s, %s, %s, %s)"
    )
    
    conn.commit()
    conn.close()

def main():
    cp_connection_params = {
        'dbname': 'control_plane_new',
        'user': 'postgres',
        'password': 'postgres',
        'host': 'localhost',
        'port': '5432'
    }
    st_connection_params = {
        'dbname': 'support_tickets_new',
        'user': 'postgres',
        'password': 'postgres',
        'host': 'localhost',
        'port': '5432'
    }
    
    insert_plans(cp_connection_params, PLANS)
    support_agent_generator.create_support_agents(5)
    
    num_users=50
   
    for _ in range(0,num_users):
        
        plan = random.choices(['free', 'base', 'advanced'], weights=[0.5, 0.3, 0.2])[0]
        # Determine project behavior pattern
        request_pattern_type = random.choices(
                ['silent', 'increasing', 'intermittent', 'decreasing', 'steady'],
                weights=[0.1, 0.2, 0.3, 0.2, 0.2]
        )[0]

        # Random price between $30-100 per model for advanced plan. Fixed for a project
        price_per_model_advanced = int(random.uniform(30, 100))
    
        ticket_frequency = random.choices(['low', 'medium', 'high'], weights=[0.4, 0.5, 0.1])[0]
    
        print('plan:', plan)
        print('request_pattern_type: ', request_pattern_type)
        print('price_per_model_advanced: ', price_per_model_advanced)
        print('ticket_frequency: ', ticket_frequency)
    
        user = user_generator.generate_and_insert_user(cp_connection_params, plan = plan, 
                                                       initial_request_pattern_type=request_pattern_type, 
                                                       price_per_model_advanced=price_per_model_advanced,
                                                       ticket_frequency=ticket_frequency)
        pprint(user)
    
        for project, plan in zip(user['projects'], user['plan_changes']):
            usage = usage_generator.generate_and_insert_usage(cp_connection_params, project_id=project['id'], request_pattern_type=request_pattern_type)
            print(usage)
            plan_changes = plan_change_generator.generate_and_insert_plan_changes(cp_connection_params, project_id=project['id'])
            print(plan_changes)
            invoices = invoice_generator.generate_and_insert_invoices(cp_connection_params, project_id=project['id'], price_per_model_advanced=price_per_model_advanced)
            print(invoices)
<<<<<<< HEAD
            
            months_diff = months_between(datetime.now(), project['created_at']) 
            if ticket_frequency == "low" and plan['name'] in ['base', 'advanced']:
                num_tickets = random.randint(0, int(months_diff/8))
            elif ticket_frequency == 'medium' and plan['name'] in ['base', 'advanced']:
                num_tickets = random.randint(1, max(1, int(months_diff/4)))
            elif ticket_frequency == 'high' and plan['name'] in ['base', 'advanced']:
                num_tickets = random.randint(2, max(2, int(months_diff/2)))
            elif ticket_frequency == "low" and plan['name'] == "free":
                num_tickets = 0
            elif ticket_frequency == "medium" and plan['name'] == "free":
                num_tickets = random.randint(0, 1)
            elif ticket_frequency == "high" and plan['name'] == "free":
                num_tickets = random.randint(0, 2)
            else:
                num_tickets = random.randint(0, 2)               
            support_tickets = support_ticket_generator.generate_and_insert_support_tickets(cp_connection_params, st_connection_params, 
                                                                                           project_id=project['id'], 
                                                                                           num_tickets=num_tickets
                                                                                           )
=======
            support_tickets = support_ticket_generator.generate_and_insert_support_tickets(cp_connection_params, st_connection_params, project_id=project['id'], 
                                                                                           support_request_pattern_type=support_request_pattern_type, 
                                                                                           ticket_frequency=ticket_frequency)
>>>>>>> origin/main
            print(support_tickets)

if __name__ == "__main__":
    main()

 

