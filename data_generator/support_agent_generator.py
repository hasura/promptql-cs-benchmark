import random
from faker import Faker
import psycopg2

def create_support_agents(num_agents=5):
    fake = Faker()
    
    try:
        conn = psycopg2.connect(
            dbname="support_tickets_new",
            user="postgres",
            password="postgres",
            host="localhost"
        )
        cursor = conn.cursor()
        
        agents = []
        
        cursor.execute(
            """
            SELECT count(*) from Support_User where role='agent'
            """
        )
        result = cursor.fetchone()
        if result:
            existing_num_agents = result[0]
        else:
            existing_num_agents = 0
            
        remaining_num_agents = num_agents - existing_num_agents
        print('existing agents: ', existing_num_agents, ', new agents to be created:', remaining_num_agents)
        for _ in range(remaining_num_agents):
            agent_id = random.randint(1000, 9999)
            email = f"{fake.first_name().lower()}.{fake.last_name().lower()}@hasura.io"
            
            cursor.execute(
                """
                INSERT INTO Support_User (id, email, role)
                VALUES (%s, %s, %s)
                """,
                (agent_id, email, "agent")
            )
            agents.append(agent_id)
            
        conn.commit()
        print(f"{num_agents} agents inserted successfully")
        
    except Exception as e:
        if conn: # type: ignore
            conn.rollback()
        print(f"Error: {str(e)}")
        
    finally:
        if cursor: # type: ignore
            cursor.close()
        if conn: # type: ignore
            conn.close()

if __name__ == "__main__":
    create_support_agents(5)