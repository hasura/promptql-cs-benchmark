import json
import random
from faker import Faker
from datetime import datetime, timedelta, timezone
import psycopg2
from psycopg2.extras import execute_values
from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from openai import OpenAI
import os

from support_ticket_generator import create_tickets

def update_tickets(num_tickets: Optional[int] = None, num_open_tickets: Optional[int] = None):
    if num_tickets is not None and num_open_tickets is not None:
        raise ValueError("Please provide either num_tickets OR num_open_tickets, not both")
    
    if num_tickets is None and num_open_tickets is None:
        raise ValueError("Please provide either num_tickets or num_open_tickets")

    # Database connection parameters
    conn = psycopg2.connect(
        dbname="support_tickets_new",
        user="postgres",
        password="postgres",
        host="localhost"
    )
    cp_conn = psycopg2.connect(
        dbname="control_plane_new",
        user="postgres",
        password="postgres",
        host="localhost"
    )

    try:
        cursor = cp_conn.cursor()
        
        # Get all projects from data_generation_seeds
        cursor.execute("""
            SELECT project_id
            FROM data_generation_seeds
            ORDER BY project_id
        """)
        
        projects = cursor.fetchall()
        
        if not projects:
            print("No projects found in data_generation_seeds table")
            return

        results = []
        errors = []
        
        # Determine which mode we're operating in and how many tickets to create
        total_tickets = num_tickets if num_tickets is not None else num_open_tickets
        is_open_only = num_open_tickets is not None

        # Create specified number of tickets
        for _ in range(total_tickets): # type: ignore
            # Randomly select a project
            project = random.choice(projects)
            project_id = project[0]  # Assuming project_id is the first column

            try:
                # Create ticket with appropriate parameters
                if is_open_only:
                    ticket_tuple = create_tickets(
                        conn,
                        cp_conn,
                        project_id=project_id,
                        num_tickets=1,
                        ticket_status='open'
                    )  # Get the single ticket ID created
                    ticket_id = ticket_tuple[0][0]
                    ticket_type = ticket_tuple[1][0]
                else:
                    ticket_tuple= create_tickets(
                        conn,
                        cp_conn,
                        project_id=project_id,
                        num_tickets=1
                    )  # Get the single ticket ID created
                    ticket_id = ticket_tuple[0][0]
                    ticket_type = ticket_tuple[1][0]
                results.append({
                    'project_id': project_id,
                    'ticket_id': ticket_id,
                    'ticket_type': ticket_type
                })
                
                print(f"Created ticket {ticket_id} for project {project_id}")
                
            except Exception as e:
                error_msg = f"Error creating ticket for project {project_id}: {str(e)}"
                print(error_msg)
                errors.append(error_msg)
                continue
        
        # Print summary
        print("\nProcessing completed!")
        print(f"Successfully created {len(results)} tickets")
        print(results)
        if errors:
            print(f"\nEncountered {len(errors)} errors:")
            for error in errors:
                print(f"- {error}")
        
        print("\nDetailed results:")
        # Group results by project_id for better readability
        project_counts = {}
        for result in results:
            pid = result['project_id']
            project_counts[pid] = project_counts.get(pid, 0) + 1
            
        for project_id, count in project_counts.items():
            print(f"Project {project_id}: Created {count} tickets")
            
        return results
            
    finally:
        conn.close()
        cp_conn.close()

if __name__ == "__main__":
    import argparse
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Create support tickets for projects')
    
    # Create mutually exclusive argument group
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--num-tickets', type=int,
                      help='Number of total tickets to create')
    group.add_argument('--num-open-tickets', type=int,
                      help='Number of open tickets to create')
    
    # Add output file argument
    parser.add_argument('--output-file', type=str, required=True,
                      help='Path to the output file to store results')
    
    args = parser.parse_args()
    results = update_tickets(num_tickets=args.num_tickets, num_open_tickets=args.num_open_tickets)
    
    # Store results in the specified output file
    try:
        with open(args.output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults have been saved to {args.output_file}")
    except Exception as e:
        print(f"Error saving results to file: {str(e)}")