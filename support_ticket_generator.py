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

@dataclass
class MetricDate:
    date: datetime
    request_count: int
    error_rate: float
    metric_type: str  # 'error' or 'request'


class TicketCategories(Enum):
    ProductionDowntime = "production_downtime"
    ProductionInstability = "production_instability"
    ProductionPerformanceDegradation = "production_performance_degradation"
    Bug = "bug"
    FeatureRequest = "feature_request"
    HowTo = "how_to"
    Others = "others"

class FeatureCategory(Enum):
    SchemaRegistry = "schema_registry"
    Actions = "actions"
    RemoteSchemas = "remote_schemas"
    EventTriggers = "event_triggers"
    Permissions = "permissions"
    GraphQL = "graphql"
    
class SupportRequestPattern(Enum):
    EASY = "easy"
    AVERAGE = "average"
    HARD = "hard"

def months_between(date1, date2):
    return (date1.year - date2.year) * 12 + (date1.month - date2.month)


def get_plan_tier(plan_name: str) -> int:
    """Return a numeric tier for plan comparison"""
    if plan_name in ['advanced', 'advanced_trial']:
        return 3
    elif plan_name in ['base', 'base_trial']:
        return 2
    else:  # free
        return 1


def get_significant_dates(cursor, project_id: str, top_n: int = 5, start_date: datetime | None = None) -> List[MetricDate]:
    """Find dates with significant metrics (high error rates or request counts)"""

    significant_dates = []

    # Get dates with high error rates
    if start_date is None:
        cursor.execute("""
            SELECT date, success_count + error_count as request_count, error_rate
            FROM Error_Rate_Daily
            WHERE project_id = %s 
            AND error_rate > 0.1  -- Significant error rate threshold
            ORDER BY error_rate DESC
            LIMIT %s
        """, (project_id, top_n))
    else:
        cursor.execute("""
            SELECT date, success_count + error_count as request_count, error_rate
            FROM Error_Rate_Daily
            WHERE project_id = %s 
            AND error_rate > 0.1  -- Significant error rate threshold
            AND date >= %s
            ORDER BY error_rate DESC
            LIMIT %s
        """, (project_id, start_date, top_n))

    for date, request_count, error_rate in cursor.fetchall():
        significant_dates.append(
            MetricDate(
                date=datetime.combine(date, datetime.min.time()),
                request_count=request_count,
                error_rate=error_rate,
                metric_type='error'
            )
        )

    # If we have enough dates, stop
    if len(significant_dates) >= top_n:
        significant_dates.sort(key=lambda x: x.date)
        return significant_dates

    cursor.execute("""
        WITH plan_changes AS (
            SELECT 
                pc1.created_at as change_date,
                p1.name as old_plan,
                p2.name as new_plan
            FROM Project_Plan_Changelogs pc1
            JOIN Project_Plan_Changelogs pc2 ON 
                pc2.project_id = pc1.project_id AND
                pc2.created_at > pc1.created_at
            JOIN Plans p1 ON p1.id = pc1.plan_id
            JOIN Plans p2 ON p2.id = pc2.plan_id
            WHERE pc1.project_id = %s AND
                pc2.created_at = (
                    SELECT MIN(pc3.created_at)
                    FROM Project_Plan_Changelogs pc3
                    WHERE pc3.project_id = pc1.project_id AND
                        pc3.created_at > pc1.created_at
                )
        )
        SELECT 
            change_date,
            old_plan,
            new_plan,
            COALESCE(r.request_count, 0) as request_count,
            COALESCE(e.error_rate, 0) as error_rate
        FROM plan_changes pc
        LEFT JOIN Requests_Daily_Count r ON 
            r.project_id = %s AND 
            r.date = pc.change_date::date
        LEFT JOIN Error_Rate_Daily e ON 
            e.project_id = %s AND 
            e.date = pc.change_date::date
        ORDER BY change_date DESC
    """, (project_id, project_id, project_id))

    # Process plan changes and find downgrades
    for date, old_plan, new_plan, request_count, error_rate in cursor.fetchall():
        # Check if this is a downgrade
        if get_plan_tier(new_plan) < get_plan_tier(old_plan):
            # Only add if not already added from previous queries
            if not any(d.date.date() == date.date() for d in significant_dates):
                significant_dates.append(
                    MetricDate(
                        date=datetime.combine(
                            date.date(), datetime.min.time()),
                        request_count=request_count,
                        error_rate=error_rate,
                        metric_type='downgrade'
                    )
                )

                # If we have enough dates, stop
                if len(significant_dates) >= top_n:
                    break

    # Sort all dates by date
    significant_dates.sort(key=lambda x: x.date)
    return significant_dates


def determine_ticket_type(metric_date: MetricDate, plan: str) -> TicketCategories:
    """Determine ticket type based on the metric that triggered the ticket"""

    # Get base request count and error rate weights
    ticket_type = random.choices([TicketCategories.ProductionDowntime,
                                  TicketCategories.ProductionInstability,
                                  TicketCategories.ProductionPerformanceDegradation,
                                  TicketCategories.Bug,
                                  TicketCategories.FeatureRequest,
                                  TicketCategories.HowTo
                                  ], weights=[
                                      0.1,
                                      0.2,
                                      0.1,
                                      0.2,
                                      0.3,
                                      0.1
                                  ])[0]

    # Override for very high error rates - force operations or bug
    if metric_date.metric_type == 'error' and metric_date.error_rate > 0.2:
        return random.choice([TicketCategories.ProductionDowntime, TicketCategories.ProductionInstability, TicketCategories.ProductionPerformanceDegradation])

    return ticket_type


def generate_message_content(
    ticket_type: TicketCategories,
    component: FeatureCategory
) -> str:
    """Generate message content based on support patterns"""
    tone_patterns = {
        SupportRequestPattern.EASY: {
            "suffixes": [
                " Thanks in advance!",
                " Appreciate your help!",
                " Looking forward to your response."
            ]
        },
        SupportRequestPattern.AVERAGE: {
            "suffixes": [
                " Please help.",
                " Please look into it.",
                " Let us know how to go about this."
            ]
        },
        SupportRequestPattern.HARD: {
            "suffixes": [
                " This needs immediate attention.",
                " Please fix this now.",
                " We have service disruption because of this."
            ]
        }
    }
    templates = {
        TicketCategories.ProductionDowntime: [
            "Production is down",
            "Cannot reach project",
            "All graphql operations returning 500",
            "Service down"
        ],
        TicketCategories.ProductionInstability: [
            "Few requests are randomly failing",
            f"{component} is randomly breaking in production.",
            f"{component} not functioning as expected in production"
            f"Erratic errors from {component}"
 
        ],
        TicketCategories.ProductionPerformanceDegradation: [
            f"Performance degradation observed in {component} operations.",
            f"High latency in {
                component} queries affecting production workload.",
            f"Resource exhaustion while using {component} in production."
            f"Slow response from {component} in production."
        ],
 
        TicketCategories.Bug: [
            f"Incorrect results from {component} when using specific filters.",
            f"Unexpected behavior in {component}.",
            f"Query returning wrong data set in {component}.",
            f"{component} not working as documented.",
            f"Permission not being correctly implemented in {component}."
            f"Security issue with {component}."
        ],
        TicketCategories.FeatureRequest: [
            f"Need environment variable support in {component}.",
            f"Request for additional functionality in {component}.",
            f"Can we have more flexibility in {component} configuration?",
            f"Enhancement request for {component} to support our use case.",
            f"Missing capability in {component} for our workflow."
        ],
        TicketCategories.HowTo: [
            f"Need help configuring {component} with custom parameters.",
            f"What's the recommended way to implement {component}?",
            f"Documentation for configuring {component} with custom settings?",
            f"Step-by-step guide needed for {component} implementation.",
            f"How to optimize {component} for our use case?"
            f"General inquiry about {component} setup."
        ],
        TicketCategories.Others: [
            f"Please move project to a different VPC.",
            f"Need access to {component} for our team.",
            f"Unable to connect {component} with our infrastructure.",
            f"TLS configuration issues when setting up {component}.",
            
        ]
    }

    if ticket_type == TicketCategories.ProductionDowntime:
        selected_pattern = SupportRequestPattern.HARD
    elif ticket_type in [TicketCategories.ProductionInstability, 
                        TicketCategories.ProductionPerformanceDegradation]:
        selected_pattern = SupportRequestPattern.AVERAGE
    else:
        selected_pattern = SupportRequestPattern.EASY
    
    
    content = random.choice(templates[ticket_type])
    suffix = random.choice(tone_patterns[selected_pattern]["suffixes"])

    return f"{content}{suffix}"


def get_project_metrics(cursor, project_id: str, date: datetime) -> Tuple[int, float]:
    """Get request count and error rate for a given date"""
    # Check requests
    cursor.execute("""
        SELECT request_count 
        FROM Requests_Daily_Count 
        WHERE project_id = %s AND date = %s
    """, (project_id, date.date()))
    request_count = cursor.fetchone()
    request_count = request_count[0] if request_count else 0

    # Check error rate
    cursor.execute("""
        SELECT error_rate 
        FROM Error_Rate_Daily 
        WHERE project_id = %s AND date = %s
    """, (project_id, date.date()))
    error_rate = cursor.fetchone()
    error_rate = error_rate[0] if error_rate else 0.0

    return request_count, error_rate


def get_project_plan(cursor, project_id: str, date: datetime) -> str:
    """Get the plan type for a project at a given date"""
    cursor.execute("""
        SELECT p.name 
        FROM Project_Plan_Changelogs pc
        JOIN Plans p ON p.id = pc.plan_id
        WHERE pc.project_id = %s 
        AND pc.created_at <= %s
        ORDER BY pc.created_at DESC 
        LIMIT 1
    """, (project_id, date))
    result = cursor.fetchone()
    return result[0] if result else "base"


def get_random_dates(
    cursor,
    project_id: str,
    project_created_at: datetime,
    remaining_dates: int,
    start_date: datetime | None = None
) -> List[MetricDate]:
    """
    Generate random dates between project creation and now, with their metrics

    Args:
        cursor: Database cursor for metrics lookup
        project_id: ID of the project
        project_created_at: Project creation timestamp
        num_dates: Number of random dates to generate

    Returns:
        List of MetricDate objects with random dates and their metrics
    """

    if remaining_dates <= 0:
        return []

    random_dates = []
    current_time = datetime.now(timezone.utc)
    if start_date is None:
        total_days = (current_time - project_created_at).days
    else:
        total_days = (current_time - start_date).days

    if total_days <= 0:
        return []

    # Generate random dates within the project's lifetime
    selected_dates = set()  # Use set to avoid duplicates
    while len(selected_dates) < remaining_dates:
        days_offset = random.randint(0, total_days)
        random_date = project_created_at + timedelta(days=days_offset)
        selected_dates.add(random_date)

    # Convert random dates to MetricDate objects
    for date in sorted(selected_dates):
        # Get metrics for this date if they exist
        cursor.execute("""
            SELECT 
                COALESCE(r.request_count, 0) as request_count,
                COALESCE(e.error_rate, 0) as error_rate
            FROM (SELECT %s::date as date) d
            LEFT JOIN Requests_Daily_Count r ON 
                r.project_id = %s AND 
                r.date = d.date
            LEFT JOIN Error_Rate_Daily e ON 
                e.project_id = %s AND 
                e.date = d.date
        """, (date.date(), project_id, project_id))

        request_count, error_rate = cursor.fetchone()
        random_dates.append(
            MetricDate(
                date=date,
                request_count=request_count,
                error_rate=error_rate,
                metric_type='random'  # Mark these as random dates
            )
        )

    return random_dates


def create_tickets(
    conn,
    cp_conn,
    project_id: str,
    ticket_frequency: str,
    start_date: datetime | None = None
) -> List[int]:
    """
    Generate support tickets based on project metrics and interaction patterns
    """
    fake = Faker()
    cursor = conn.cursor()
    cp_cursor = cp_conn.cursor()

    # Get project creation date
    cp_cursor.execute("""
        SELECT created_at, owner_id 
        FROM Projects 
        WHERE id = %s
    """, (project_id,))
    project_data = cp_cursor.fetchone()
    if not project_data:
        raise Exception("Project not found")

    project_created_at, owner_id = project_data

    months_diff = months_between(datetime.now(), project_created_at)
    print('MONTHS_DIFF: ', months_diff)
    
    project_plan = get_project_plan(cp_cursor, project_id=project_id, date=datetime.now(timezone.utc))

    if ticket_frequency == "low" and project_plan in ['base', 'advanced']:
        num_tickets = random.randint(0, int(months_diff/8))
    elif ticket_frequency == 'medium' and project_plan in ['base', 'advanced']:
        num_tickets = random.randint(1, max(1, int(months_diff/4)))
    elif ticket_frequency == 'high' and project_plan in ['base', 'advanced']:
        num_tickets = random.randint(2, max(2, int(months_diff/2)))
    elif ticket_frequency == "low" and project_plan == "free":
        num_tickets = 0
    elif ticket_frequency == "medium" and project_plan == "free":
        num_tickets = random.randint(0, 1)
    elif ticket_frequency == "high" and project_plan == "free":
        num_tickets = random.randint(0, 2)
    else:
        num_tickets = random.randint(0, 2)

    print('number of support tickets to generate: ', num_tickets,
          ', plan: ', project_plan, ', ticket frequency: ', ticket_frequency)

    # Get significant dates for ticket creation
    significant_dates = get_significant_dates(
        cp_cursor, project_id, num_tickets)
    if not significant_dates:
        print("WARNING: No significant metric dates found for project")

    more_dates = get_random_dates(
        cp_cursor, project_id, project_created_at, num_tickets - len(significant_dates))

    ticket_dates = (significant_dates + more_dates)[0:num_tickets]

    cp_cursor.execute("""
        SELECT email 
        FROM Users 
        WHERE id = %s
    """, (owner_id,))
    user_email = cp_cursor.fetchone()[0]

    # Insert or get requester ID from Support_User table
    cursor.execute("""
        INSERT INTO Support_User (email, role)
        VALUES (%s, 'user')
        ON CONFLICT (email) DO NOTHING
        RETURNING id
    """, (user_email,))
    result = cursor.fetchone()

    if result:
        requester_support_id = result[0]
    else:
        # If no ID returned from insert (due to ON CONFLICT), get the existing ID
        cursor.execute("""
            SELECT id FROM Support_User 
            WHERE email = %s AND role = 'user'
        """, (user_email,))
        requester_support_id = cursor.fetchone()[0]

    # Get agent IDs
    cursor.execute("SELECT id FROM Support_User WHERE role = 'agent'")
    agent_ids = [row[0] for row in cursor.fetchall()]
    if not agent_ids:
        raise Exception("No support agents found")

    tickets = []
    # Create tickets for each significant date
    for metric_date in ticket_dates:
        # Get project plan for this date
        plan = get_project_plan(cp_cursor, project_id, metric_date.date)

        # Determine ticket type based on metrics
        ticket_type = determine_ticket_type(metric_date, plan)
        component = random.choice(list(FeatureCategory))

        # Generate ticket content
        proto_description = generate_message_content(
            ticket_type,
            component
        )

        created_at = metric_date.date + timedelta(hours=random.randint(1, 8))

        maybe_content = get_ai_generated_description(proto_description)
        if maybe_content:
            subject, description = maybe_content
            print(subject + ":\n")
            print(description)
            print("\n\n")

            description = f"{description}\n\nProject ID: {project_id}\n"
            ticket = {
                "is_public": True,
                "priority": None,
                "status": "open",
                "subject": subject,
                "description": description,
                "type": random.choices([None, str(ticket_type)], weights=[0.75, 0.25])[0],
                # Using Support_User agent ID
                "assignee_id": random.choice(agent_ids),
                "requester_id": requester_support_id,     # Using Support_User customer ID
                "created_at": created_at,
            }
            tickets.append(ticket)

    # Insert tickets
    insert_query = """
        INSERT INTO Support_Ticket (
            is_public, priority, status, subject, description, type,
            assignee_id, requester_id, created_at
        ) VALUES (
            %(is_public)s, %(priority)s, %(status)s, %(subject)s, 
            %(description)s, %(type)s, %(assignee_id)s, %(requester_id)s, 
            %(created_at)s
        ) RETURNING id
    """

    ticket_ids = []
    for ticket in tickets:
        cursor.execute(insert_query, ticket)
        ticket_id = cursor.fetchone()[0]
        ticket_ids.append(ticket_id)
        response_pattern = random.choices(
            ['smooth', 'average', 'struggling'], weights=[0.25, 0.5, 0.25])[0]
        if ticket['priority'] == 'high':
            num_comments = random.randint(4, 10)
            status = random.choices(
                ['open', 'pending', 'closed'], weights=[0.2, 0.1, 0.7])[0]
        elif ticket['priority'] == 'medium':
            num_comments = random.randint(0, 6)
            status = random.choices(
                ['open', 'pending', 'closed'], weights=[0.2, 0.3, 0.5])[0]
        elif ticket['priority'] == 'low':
            num_comments = random.randint(0, 4)
            status = random.choices(
                ['open', 'pending', 'closed'], weights=[0.5, 0.3, 0.2])[0]
        else:
            num_comments = random.randint(0, 2)
            status = random.choices(
                ['open', 'pending', 'closed'], weights=[0.3, 0.3, 0.4])[0]

        if status == "closed":
            num_comments = num_comments + 1  # avoid

        print('EXPECTED STATUS: ', status)
        status, ticket_comments = get_ai_generated_ticket_comments(
            ticket['description'], ticket['created_at'], status, num_comments, response_pattern)
        print('status: ', status)
        print(ticket_comments)

        ticket_comments_values = [(ticket_id, comment['body'], comment['created_at'], ticket['requester_id']
                                   if comment['role'] == 'user' else ticket['assignee_id']) for comment in ticket_comments]

        execute_values(
            cursor,
            """
            INSERT INTO Support_Ticket_Comment(ticket_id, body, created_at, user_id)
            VALUES %s
            """,
            ticket_comments_values,
            template="(%s, %s, %s, %s)"
        )

        cursor.execute("""
                       UPDATE Support_Ticket SET status = %s where id = %s
                       """, (status, ticket_id))

    conn.commit()
    cp_conn.commit()
    return ticket_ids


def get_ai_generated_description(proto_description)  -> Tuple[str, str] | None:

    with open('sample_support_conversations.txt', 'r') as file:
        sample_tickets = file.read()

    system_prompt = f"""

Sample tickets with subject, description and comments for reference:

{sample_tickets}

You are supposed to generate fake support tickets for an API SaaS company. You will be given some initial context. You need to create a realistic subject and description for this ticket as coming from a genuine user.

Be straightforward in your description.

IMPORTANT GUIDELINES:
1. If dealing with bug, feature requests or how-to tickets, add names of database(s) that the customer might be using in the description, popular ones being Postgres, Snowflake, MySQL, MongoDB and SQL Server. Less popular ones being BigQuery, Oracle
2. For bug or production issues, add a software version somewhere in the description like this "Version: v2.41.0". Versions are in the form "v2.x.x" where the max version is "v2.50.10"

Generate a json like `{{"subject": string, "description": string}}` . Always return a valid JSON object, without any additional text or formatting.


"""

    try:

        OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
        if not OPENAI_API_KEY:
            print("Error: OPENAI_API_KEY not found in environment variables")
            print("Please create a .env file with your OpenAI API key like this:")
            print("OPENAI_API_KEY=your-api-key-here")
            exit(1)
        client = OpenAI(api_key=OPENAI_API_KEY)
        completion = client.chat.completions.create(
            model="o1-preview",
            messages=[
                # {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"""
                 
{system_prompt}


Generate subject and description based on:
Context: {proto_description}
"""
                }
            ],
        )

        chat_message = json.loads(
            completion.choices[0].message.content)  # type: ignore
        print(chat_message)
        return (chat_message['subject'], chat_message['description'])
    except Exception as e:
        # Handle errors from OpenAI's API
        print(f"An error occurred: {e}")
        return None


def get_ai_generated_ticket_comments(description: str, created_at: datetime, status: str, num_comments: int, response_pattern: str) -> Tuple[str, List[Dict]]:

    with open('sample_support_conversations.txt', 'r') as file:
        sample_tickets = file.read()

    system_prompt = f"""
You are supposed to generate fake support tickets comments for an API SaaS company.

You will be provided with `num_comments` to denote the expected length of the conversation.

You will also be given `created_at` so the comments should be after this time (each comment could range from few hours to few days after the previous comment)

You will also be given a `status` which can be one of `open`, `pending` or `closed`. It is very IMPORTANT to generate the comments based on the status.
`open` status means that the last comment would mean that the support agent needs to follow up.
`pending` status means that the user has to furnish more information or confirm some data. This usually means that the last comment is from an agent asking for more information
`closed` status means that the ticket has been successfully resolved. This usually means that the last comment is from the user and has acknowledged the successful resolution.

Note that you may be given a field called agent_response_pattern which would be one of smooth, average or struggling. You should use this to generate the general quality of response from an agent

Generate a json which has the status and an array of comments following the shape: `{{ "status": <open or pending or closed>, "comments": [{{"body": string, "created_at": timestamptz, "role" : <user or agent>}}] }}` .
Always return a valid JSON object, without any additional text or formatting.

Sample tickets with subject, description and comments for reference:

{sample_tickets}
"""

    try:

        OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
        if not OPENAI_API_KEY:
            print("Error: OPENAI_API_KEY not found in environment variables")
            print("Please create a .env file with your OpenAI API key like this:")
            print("OPENAI_API_KEY=your-api-key-here")
            exit(1)
        client = OpenAI(api_key=OPENAI_API_KEY)
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"""
Generate comments with the following properties
- created_at: {created_at}
- status: {status}
- num_comments: {num_comments}
- agent_response_pattern: {response_pattern}
- description: {description}
"""
                }
            ],
            temperature=0.7,
            max_tokens=10000
        )

        chat_message = json.loads(
            completion.choices[0].message.content)  # type: ignore
        print("expected num_comments: ", num_comments)
        print("status: ", chat_message['status'])
        print(chat_message['comments'])
        return chat_message['status'], chat_message['comments']
    except Exception as e:
        # Handle errors from OpenAI's API
        print(f"An error occurred: {e}")
        return 'open', []


def generate_and_insert_support_tickets(cp_connection_params, st_connection_params, project_id, support_request_pattern_type, ticket_frequency):
    conn = psycopg2.connect(**st_connection_params)

    cp_conn = psycopg2.connect(**cp_connection_params)

    try:
        # Create tickets for a specific project
        ticket_ids = create_tickets(
            conn,
            cp_conn,
            project_id,
            support_request_pattern_type,
            ticket_frequency
        )
        print(f"Created {len(ticket_ids)} tickets with IDs: {ticket_ids}")
        return ticket_ids

    finally:
        conn.close()
        cp_conn.close()

def update_tickets():
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
            SELECT project_id, ticket_frequency 
            FROM data_generation_seeds
            order by project_id
        """)
        
        projects = cursor.fetchall()
        
        if not projects:
            print("No projects found in data_generation_seeds table")
            return
        
        results = []
        errors = []
        
        # Process each project
        for project_id, ticket_frequency in projects:
            try:
                print(f"Processing project: {project_id} with frequency: {ticket_frequency}")
                
                # Create tickets for this project
                ticket_ids = create_tickets(
                    conn,
                    cp_conn,
                    project_id=project_id,
                    ticket_frequency=ticket_frequency
                )
                
                results.append({
                    'project_id': project_id,
                    'tickets_created': len(ticket_ids),
                    'ticket_ids': ticket_ids
                })
                
                print(f"Created {len(ticket_ids)} tickets for project {project_id}")
                
            except Exception as e:
                error_msg = f"Error processing project {project_id}: {str(e)}"
                print(error_msg)
                errors.append(error_msg)
                raise e
                continue
        
        # Print summary
        print("\nProcessing completed!")
        print(f"Successfully processed {len(results)} projects")
        if errors:
            print(f"\nEncountered {len(errors)} errors:")
            for error in errors:
                print(f"- {error}")
        
        print("\nDetailed results:")
        for result in results:
            print(f"Project {result['project_id']}: Created {result['tickets_created']} tickets")
            
    finally:
        conn.close()
        cp_conn.close()

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "update_tickets":
        update_tickets()
    else:
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
            # Create tickets for a specific project
            ticket_ids = create_tickets(
                conn,
                cp_conn,
                project_id="1b40dfe0-02f6-4e2c-aaf8-b275434b2dae",
                ticket_frequency='high',
                # start_date = datetime(2024, 11, 1)
            )
            print(f"Created {len(ticket_ids)} tickets with IDs: {ticket_ids}")

        finally:
            conn.close()
            cp_conn.close()
