import uuid
from datetime import datetime, timedelta, timezone
import random
from typing import List, Dict, Optional
import psycopg2
from psycopg2.extras import execute_values

class PlanChangelogGenerator:
    def __init__(self, connection_params: Dict):
        self.conn = psycopg2.connect(**connection_params)
        self.cursor = self.conn.cursor()
        self.plans = self._get_plans()
        
    def _get_plans(self) -> Dict[str, str]:
        """Fetch all plans and store their IDs"""
        self.cursor.execute("SELECT id, name FROM Plans")
        return {row[1]: str(row[0]) for row in self.cursor.fetchall()}  # Convert UUID to string
    
    def _add_jitter(self, base_date: datetime, days: int, jitter_days: int = 7) -> datetime:
        """Add random jitter to a base date within specified range
        
        Args:
            base_date: Original datetime
            days: Number of days to add to base_date
            jitter_days: Maximum number of days to adjust by (plus or minus)
            
        Returns:
            datetime with jitter applied
        """
        # Add random days jitter
        jitter_days = random.randint(-jitter_days, jitter_days)
        
        # Add random seconds jitter (up to ±12 hours in seconds)
        jitter_seconds = random.randint(-43200, 43200)
        
        return base_date + timedelta(days=days + jitter_days, seconds=jitter_seconds)
    
    def get_request_pattern_type(self, project_id: str) -> str:
        self.cursor.execute("SELECT initial_request_pattern_type from data_generation_seeds where project_id=%s", (project_id,))
        result = self.cursor.fetchone()
        if result is None:
            raise ValueError(f"No data found for project_id: {project_id}")
        return result[0]
    
    def generate_changelogs(self, project_id: str, pattern_type: str) -> List[Dict]:
        """Generate changelog entries for a project"""
        try:
            # Get project info
            self.cursor.execute("""
                SELECT p.id, p.created_at, pl.name as plan_name, p.deleted_at
                FROM Projects p
                JOIN Project_Plan_Changelogs pc ON p.id = pc.project_id
                JOIN Plans pl ON pc.plan_id = pl.id
                WHERE p.id = %s
                ORDER BY pc.created_at ASC
                LIMIT 1
            """, (project_id,))
            
            project = dict(zip(['id', 'created_at', 'plan_name', 'deleted_at'], 
                             self.cursor.fetchone()))
            
            # Determine plan changes
            changes = self.determine_plan_changes(project, pattern_type)
            
            # Convert changes to changelog entries
            changelogs = []
            for change in changes:
                changelogs.append({
                    'id': str(uuid.uuid4()),  # Convert UUID to string
                    'plan_id': self.plans[change['target_plan']],
                    'project_id': str(project_id),  # Convert UUID to string
                    'comment': change['comment'],
                    'created_at': change['date']
                })
            
            # Update project deleted_at if needed
            if project.get('deleted_at'):
                self.cursor.execute("""
                    UPDATE Projects
                    SET deleted_at = %s
                    WHERE id = %s
                """, (project['deleted_at'], project_id))
            
            return changelogs
            
        except Exception as e:
            self.conn.rollback()
            raise e

    def determine_plan_changes(self, project: Dict, pattern_type: str) -> List[Dict]:
        """Determine plan changes based on pattern type and current plan"""
        changes = []
        project_created = project['created_at']
        current_plan = project['plan_name']
        
        three_months_later = self._add_jitter(project_created, 90)  # ~3 months ± 1 week
        six_months_later = self._add_jitter(project_created, 180)   # ~6 months ± 1 week
        one_year_later = self._add_jitter(project_created, 365)     # ~1 year ± 1 week
        
        if current_plan == 'free':
            if pattern_type == 'increasing':
                # 50% chance to upgrade to base after 3 months
                if three_months_later < datetime.now(timezone.utc):
                    if random.random() < 0.5:
                        changes.append({
                            'target_plan': 'base',
                            'date': three_months_later,
                            'comment': 'Upgrade to base plan due to increasing usage'
                        })
                # 20% chance to upgrade to advanced after 1 year
                elif random.random() < 0.2:
                    if one_year_later < datetime.now(timezone.utc):
                        
                        changes.append({
                            'target_plan': 'advanced',
                            'date': one_year_later,
                            'comment': 'Upgrade to advanced plan due to sustained growth'
                        })
                    
            elif pattern_type == 'intermittent':
                # 25% chance to upgrade to base after 3 months
                if random.random() < 0.25:
                    if three_months_later < datetime.now(timezone.utc):
                        changes.append({
                            'target_plan': 'base',
                            'date': three_months_later,
                            'comment': 'Upgrade to base plan for intermittent high usage'
                        })
                    
            elif pattern_type == 'steady':
                # 25% chance to upgrade to base after 1 year
                if random.random() < 0.25:
                    if one_year_later < datetime.now(timezone.utc):
                        changes.append({
                            'target_plan': 'base',
                            'date': one_year_later,
                            'comment': 'Upgrade to base plan due to steady usage'
                        })
                # 10% chance to upgrade to advanced after 1 year
                elif random.random() < 0.1:
                    if one_year_later < datetime.now(timezone.utc):
                        changes.append({
                            'target_plan': 'advanced',
                            'date': one_year_later,
                            'comment': 'Upgrade to advanced plan due to sustained steady usage'
                        })

        elif current_plan == 'base':
            if pattern_type == 'silent':
                if random.random() < 0.5:  # 50% chance to downgrade to free
                    if one_year_later < datetime.now(timezone.utc):
                        changes.append({
                            'target_plan': 'free',
                            'date': one_year_later,
                            'comment': 'Downgrade to free plan due to inactivity'
                        })
                elif random.random() < 0.25:  # 25% chance to delete
                    if one_year_later < datetime.now(timezone.utc):
                        project['deleted_at'] = one_year_later
                    
            elif pattern_type == 'increasing':
                if random.random() < 0.25:  # 25% chance to upgrade after 6 months
                    if six_months_later < datetime.now(timezone.utc):
                        changes.append({
                            'target_plan': 'advanced',
                            'date': six_months_later,
                            'comment': 'Early upgrade to advanced plan due to rapid growth'
                        })
                elif random.random() < 0.75:  # 75% chance to upgrade after a year
                    if one_year_later < datetime.now(timezone.utc):
                        changes.append({
                            'target_plan': 'advanced',
                            'date': one_year_later,
                            'comment': 'Upgrade to advanced plan due to sustained growth'
                        })
                    
            elif pattern_type == 'intermittent':
                if random.random() < 0.25:  # 25% chance to upgrade
                    if one_year_later < datetime.now(timezone.utc):
                        changes.append({
                            'target_plan': 'advanced',
                            'date': one_year_later,
                            'comment': 'Upgrade to advanced plan for periodic high usage'
                        })
                elif random.random() < 0.1:  # 10% chance to downgrade
                    if one_year_later < datetime.now(timezone.utc):
                        changes.append({
                            'target_plan': 'free',
                            'date': one_year_later,
                            'comment': 'Downgrade to free plan due to sporadic usage'
                        })
                    
            elif pattern_type == 'decreasing':
                if random.random() < 0.25:  # 25% chance to downgrade
                    if one_year_later < datetime.now(timezone.utc):
                        changes.append({
                            'target_plan': 'free',
                            'date': one_year_later,
                            'comment': 'Downgrade to free plan due to decreased usage'
                        })

        elif current_plan == 'advanced':
            if pattern_type == 'silent':
                if random.random() < 0.5:  # 50% chance to downgrade to base
                    if one_year_later < datetime.now(timezone.utc):
                        changes.append({
                            'target_plan': 'base',
                            'date': one_year_later,
                            'comment': 'Downgrade to base plan due to reduced activity'
                        })
                else:  # 50% chance to downgrade to free
                    if one_year_later < datetime.now(timezone.utc):
                        changes.append({
                            'target_plan': 'free',
                            'date': one_year_later,
                            'comment': 'Downgrade to free plan due to minimal usage'
                        })
                    
            elif pattern_type in ['intermittent', 'decreasing', 'steady']:
                if random.random() < 0.25:  # 25% chance to downgrade to base
                    if one_year_later < datetime.now(timezone.utc):
                        changes.append({
                            'target_plan': 'base',
                            'date': one_year_later,
                            'comment': f'Downgrade to base plan due to {pattern_type} usage pattern'
                        })
        
        return changes
    
    def insert_changelogs(self, changelogs: List[Dict]):
        """Insert changelog entries into database"""
        if not changelogs:
            return
            
        execute_values(
            self.cursor,
            """
            INSERT INTO Project_Plan_Changelogs (id, plan_id, project_id, comment, created_at)
            VALUES %s
            ON CONFLICT (id) DO NOTHING
            """,
            [(
                log['id'], log['plan_id'], log['project_id'],
                log['comment'], log['created_at']
            ) for log in changelogs],
            template="(%s, %s, %s, %s, %s)"
        )
        
        self.conn.commit()
    
    def close(self):
        """Close database connection"""
        self.cursor.close()
        self.conn.close()

def generate_and_insert_plan_changes(connection_params, project_id):
    try:
        generator = PlanChangelogGenerator(connection_params)
        
        # Example usage for a specific project
        pattern_type = generator.get_request_pattern_type(project_id=project_id)
        
        changelogs = generator.generate_changelogs(project_id, pattern_type)
        generator.insert_changelogs(changelogs)
        
        print(f"Generated {len(changelogs)} plan changes for project {project_id}")
        return changelogs
        
    except Exception as e:
        print(f"Error occurred: {e}")
        raise
    finally:
        generator.close() # type: ignore    

def main():
    connection_params = {
        'dbname': 'control_plane_new',
        'user': 'postgres',
        'password': 'postgres',
        'host': 'localhost',
        'port': '5432'
    }
    
    try:
        generator = PlanChangelogGenerator(connection_params)
        
        # Example usage for a specific project
        project_id = "a1596b61-18ce-4f7e-a516-9e67e5175738"
        pattern_type = generator.get_request_pattern_type(project_id=project_id)
        
        changelogs = generator.generate_changelogs(project_id, pattern_type)
        print(changelogs)
        generator.insert_changelogs(changelogs)
        
        print(f"Generated {len(changelogs)} plan changes for project {project_id}")
        
    except Exception as e:
        print(f"Error occurred: {e}")
        raise
    finally:
        generator.close() # type: ignore

if __name__ == "__main__":
    main()