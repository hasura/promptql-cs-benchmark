import uuid
from datetime import datetime, timedelta
import random
from faker import Faker
from typing import List, Dict
import json

import psycopg2
from psycopg2.extras import execute_values

fake = Faker()


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

def get_standard_plans():
    standard_names = ["free", "base", "advanced"]
    return [plan for plan in PLANS if plan["name"] in standard_names]

class UserProjectGenerator:
    def __init__(self, start_date: datetime = datetime(2023, 1, 1),
                 end_date: datetime = datetime.now()):
        self.start_date = start_date
        self.end_date = end_date
        self.plans = get_standard_plans()
        
    def generate_user(self) -> Dict:
        """Generate a single user"""
        first_name = fake.first_name()
        last_name = fake.last_name()
        company_domain = fake.domain_name()
        created_at = fake.date_time_between(start_date=self.start_date, end_date=self.end_date)
        
        return {
            'id': str(uuid.uuid4()),
            'email': f"{first_name.lower()}.{last_name.lower()}@{company_domain}",
            'customer_id': f"cus_{uuid.uuid4().hex[:16]}",
            'created_at': created_at,
            'updated_at': created_at,
            'first_name': first_name,
            'last_name': last_name
        }
    
    def generate_projects(self, user_id: str, user_created_at: datetime) -> List[Dict]:
        """Generate projects for a user based on probability distribution"""
        # Determine number of projects
        prob = random.random()
        if prob < 0.60:  # 60% chance of 1 project
            num_projects = 1
        elif prob < 0.30:  # 30% chance of 2 projects
            num_projects = 2
        else:  # 10% chance of 3-4 projects
            num_projects = random.randint(3, 4)
        
        projects = []
        for _ in range(num_projects):
            # Generate project creation date after user creation
            created_at = fake.date_time_between(
                start_date=user_created_at,
                end_date=self.end_date
            )
            
            # 10% chance of project being deleted
            deleted_at = None
            if random.random() < 0.1:
                deleted_at = fake.date_time_between(
                    start_date=created_at + timedelta(days=30),  # At least 30 days active
                    end_date=self.end_date
                )
            
            projects.append({
                'id': str(uuid.uuid4()),
                'name': f"{fake.word()}-{fake.word()}-{random.randint(1000, 9999)}",
                'owner_id': user_id,
                'created_at': created_at,
                'updated_at': created_at,
                'deleted_at': deleted_at,
                'active_models': random.randint(5,100)
            })
        
        return projects
    
    def generate_initial_plan(self, project_id: str, project_created_at: datetime, possible_plans: List[str]) -> Dict:
        """Generate only initial plan assignment for a project"""
        filtered_plans = [plan for plan in PLANS if plan["name"] in possible_plans]
        # Initial plan distribution: 50% free, 30% base, 20% advanced
        initial_plan = random.choices(
            filtered_plans
        )[0]
        
        return {
            'id': str(uuid.uuid4()),
            'plan_id': initial_plan['id'],
            'project_id': project_id,
            'comment': 'Initial plan assignment',
            'created_at': project_created_at,
            'name': initial_plan['name']
        }

    def generate_complete_dataset(self, plan:str) -> Dict:
        """Generate complete dataset with specified number of users"""
        dataset = {
            'user': {} ,
            'projects': [],
            'plan_changes': []
        }
        
        # Generate user
        user = self.generate_user()
        dataset['user'] = user
        
        # Generate projects for user
        projects = self.generate_projects(user['id'], user['created_at'])
        dataset['projects'].extend(projects)
        
        first_project_plan = self.generate_initial_plan(projects[0]['id'], projects[0]['created_at'], [plan])
        dataset['plan_changes'].append(first_project_plan)
        
        possible_plans = []
        if plan == "free":
            possible_plans = ["free"]
        elif plan == "base":
            possible_plans = ["free", "base"]
        elif plan == "advanced":
            possible_plans = ["free", "base", "advanced"]
        
        # Generate initial plan for remaining projects
        for project in projects[1:]:
            initial_plan = self.generate_initial_plan(
                project['id'],
                project['created_at'],
                possible_plans
            )
            dataset['plan_changes'].append(initial_plan)
        
        return dataset

class DatabaseInserter:
    def __init__(self, connection_params: Dict):
        self.conn = psycopg2.connect(**connection_params)
        self.cursor = self.conn.cursor()


        

    def insert_user(self, user: Dict):
        """Insert user data"""
        user_values = [
            (user['id'], user['email'], user['customer_id'], 
             user['created_at'], user['updated_at'],
             user['first_name'], user['last_name'])
        ]
        
        execute_values(
            self.cursor,
            """
            INSERT INTO Users (id, email, customer_id, created_at, updated_at,
                             first_name, last_name)
            VALUES %s
            """,
            user_values,
            template="(%s, %s, %s, %s, %s, %s, %s)"
        )

    def insert_projects(self, projects: List[Dict]):
        """Insert project data"""
        project_values = [
            (project['id'], project['name'], project['owner_id'],
            project['created_at'], project['updated_at'], project['deleted_at'],
            project['active_models'])
            for project in projects
        ]

        execute_values(
            self.cursor,
            """
            INSERT INTO Projects (id, name, owner_id, created_at, updated_at, deleted_at, active_models)
            VALUES %s
            """,
            project_values,
            template="(%s, %s, %s, %s, %s, %s, %s)"
        )

    def insert_plan_changes(self, plan_changes: List[Dict]):
        """Insert plan change data"""
        plan_change_values = [
            (change['id'], change['plan_id'], change['project_id'],
             change['comment'], change['created_at'])
            for change in plan_changes
        ]
        
        execute_values(
            self.cursor,
            """
            INSERT INTO Project_Plan_Changelogs (id, plan_id, project_id,
                                               comment, created_at)
            VALUES %s
            """,
            plan_change_values,
            template="(%s, %s, %s, %s, %s)"
        )
        
    def insert_data_generation_seeds(self, projects: List[Dict], initial_request_pattern_type: str, price_per_model_advanced: int, support_request_pattern_type: str, ticket_frequency: str):
        project_values = [
            (project['id'], initial_request_pattern_type, price_per_model_advanced, support_request_pattern_type, ticket_frequency) for project in projects
        ]

        execute_values(
            self.cursor,
            """
            INSERT INTO data_generation_seeds(project_id, initial_request_pattern_type, price_per_model_advanced, support_request_pattern_type, ticket_frequency)
            VALUES %s
            """,
            project_values,
        )        

    def commit(self):
        """Commit the transaction"""
        self.conn.commit()

    def close(self):
        """Close the database connection"""
        self.cursor.close()
        self.conn.close()
        
def generate_and_insert_user(connection_params: Dict[str, str], 
                           plan:str,
                           initial_request_pattern_type: str,
                           price_per_model_advanced: int,
                           support_request_pattern_type: str,
                           ticket_frequency: str,
                           start_date: datetime = datetime(2022, 1, 1),
                           end_date: datetime = datetime.now(),
                           ) -> Dict:
    """
    Generate a single user with projects and plan changes and insert into database.
    
    Args:
        connection_params: Database connection parameters
        start_date: Start date for data generation
        end_date: End date for data generation
        
    Returns:
        Dict containing the generated data
    """
    try:
        # Initialize generator and inserter
        generator = UserProjectGenerator(start_date, end_date)
        db_inserter = DatabaseInserter(connection_params)
        
        # Generate data
        dataset = generator.generate_complete_dataset(plan)
        
        # Insert data
        db_inserter.insert_user(dataset['user'])
        db_inserter.insert_projects(dataset['projects'])
        db_inserter.insert_plan_changes(dataset['plan_changes'])
        db_inserter.insert_data_generation_seeds(dataset['projects'], initial_request_pattern_type, price_per_model_advanced, support_request_pattern_type, ticket_frequency)
        
        # Commit and close
        db_inserter.commit()
        return dataset
        
    except Exception as e:
        print(f"Error occurred: {e}")
        raise
    finally:
        if 'db_inserter' in locals():
            db_inserter.close() # type: ignore
        
def main():
    # Database connection parameters
    connection_params = {
        'dbname': 'control_plane_new',
        'user': 'postgres',
        'password': 'postgres',
        'host': 'localhost',
        'port': '5432'
    }

    # Initialize generators
    generator = UserProjectGenerator()
    
    try:
        # Initialize database inserter
        db_inserter = DatabaseInserter(connection_params)
        
        
        # Generate and insert data
        dataset = generator.generate_complete_dataset(plan="base")  # Adjust plan as needed
        
        db_inserter.insert_user(dataset['user'])
        db_inserter.insert_projects(dataset['projects'])
        db_inserter.insert_plan_changes(dataset['plan_changes'])
        db_inserter.insert_data_generation_seeds(dataset['projects'], "intermittent", 60, "average", "medium")
        
        # Commit the transaction
        db_inserter.commit()
        print("Data insertion completed successfully!")
        
    except Exception as e:
        print(f"Error occurred: {e}")
        raise
    finally:
        db_inserter.close() # type: ignore

if __name__ == "__main__":
    main()