import uuid
from datetime import datetime, timedelta
import random
from faker import Faker
import numpy as np
from typing import List, Tuple, Dict
import json
import psycopg2
from psycopg2.extras import execute_values

class RequestPatternGenerator:
    def __init__(self, start_date: datetime, end_date: datetime):
        self.start_date = start_date
        self.end_date = end_date
        self.total_days = (end_date - start_date).days

    def generate_silent_pattern(self, base_volume: int) -> List[int]:
        """Generate pattern for silent projects - initial activity then dies off"""
        active_days = random.randint(14, 30)   # Active for 2-4 weeks
        daily_requests = []
        
        # Initial activity period
        for day in range(active_days):
            # Gradual decline in initial period
            decay_factor = 1 - (day / active_days)
            requests = int(base_volume * decay_factor * random.uniform(0.8, 1.2))
            daily_requests.append(max(0, requests))
        
        # Remaining days with zero or near-zero activity
        remaining_days = self.total_days - active_days
        daily_requests.extend([0 for _ in range(remaining_days)])
        
        return daily_requests

    def generate_increasing_pattern(self, base_volume: int) -> List[int]:
        """Generate pattern for steadily increasing projects"""
        daily_requests = []
        growth_factor = random.uniform(1.0001, 1.0003)  # Subtle daily growth
        
        current_volume = base_volume * random.uniform(0.3, 0.5)  # Start lower
        for _ in range(self.total_days):
            # Add some daily noise
            noise = random.uniform(0.8, 1.2)
            requests = int(current_volume * noise)
            daily_requests.append(max(0, requests))
            
            # Grow base volume
            current_volume *= growth_factor
            
            # Add occasional growth spikes (5% chance)
            if random.random() < 0.05:
                current_volume *= random.uniform(1.1, 1.3)
        
        return daily_requests

    def generate_intermittent_pattern(self, base_volume: int) -> List[int]:
        """Generate pattern for intermittent projects with sporadic activity"""
        daily_requests = []
        
        # Define several active periods
        active_periods = []
        current_day = 0
        while current_day < self.total_days:
            # Random active period of 3-14 days
            period_length = random.randint(3, 14)
            # Random gap of 10-30 days
            gap_length = random.randint(10, 30)
            
            active_periods.append((current_day, current_day + period_length))
            current_day += period_length + gap_length
        
        # Generate requests
        for day in range(self.total_days):
            # Check if day is in active period
            is_active = any(start <= day <= end for start, end in active_periods)
            
            if is_active:
                # Higher volume during active periods
                requests = int(base_volume * random.uniform(0.8, 1.5))
            else:
                # Low volume during inactive periods
                requests = int(base_volume * random.uniform(0, 0.1))
            
            daily_requests.append(max(0, requests))
        
        return daily_requests

    def generate_decreasing_pattern(self, base_volume: int) -> List[int]:
        """Generate pattern for projects that increase then decrease"""
        daily_requests = []
        
        # Define peak point (somewhere between 1/3 and 2/3 of the timeline)
        peak_day = random.randint(self.total_days // 3, (2 * self.total_days) // 3)
        
        # Growth phase
        current_volume = base_volume * random.uniform(0.3, 0.5)
        growth_factor = np.exp(np.log(3) / peak_day)  # Triple volume by peak
        
        for day in range(peak_day):
            noise = random.uniform(0.8, 1.2)
            requests = int(current_volume * noise)
            daily_requests.append(max(0, requests))
            current_volume *= growth_factor
        
        # Decline phase
        decline_days = self.total_days - peak_day
        decay_factor = np.exp(np.log(0.1) / decline_days)  # Decay to 20% of peak
        
        for day in range(decline_days):
            noise = random.uniform(0.8, 1.2)
            requests = int(current_volume * noise)
            daily_requests.append(max(0, requests))
            current_volume *= decay_factor
        
        return daily_requests
    
    def generate_steady_pattern(self, base_volume: int) -> List[int]:
        """Generate pattern for steadily active projects with consistent usage"""
        daily_requests = []
        
        # Define base variation parameters
        daily_noise_factor = 0.2  # 20% daily variation
        weekly_cycle_amplitude = 0.3  # 30% weekly cycle variation
        monthly_cycle_amplitude = 0.15  # 15% monthly cycle variation
        
        for day in range(self.total_days):
            # Add daily random noise
            noise = random.uniform(1 - daily_noise_factor, 1 + daily_noise_factor)
            
            # Add weekly cycle (lower on weekends)
            week_day = day % 7
            weekend_factor = 1.0 - (weekly_cycle_amplitude if week_day >= 5 else 0)
            
            # Add monthly cycle (slight increase during middle of month)
            month_day = day % 30
            monthly_factor = 1.0 + (monthly_cycle_amplitude * np.sin(2 * np.pi * month_day / 30))
            
            # Calculate requests for the day
            requests = int(base_volume * noise * weekend_factor * monthly_factor)
            
            # Add occasional spikes (1% chance)
            if random.random() < 0.01:
                requests = int(requests * random.uniform(1.5, 2.0))
            
            # Add occasional dips (1% chance)
            if random.random() < 0.01:
                requests = int(requests * random.uniform(0.5, 0.8))
            
            daily_requests.append(max(0, requests))
        
        return daily_requests

    def generate_error_rates(self, requests: List[int], base_error_rate: float) -> List[int]:
        """Generate realistic error counts based on request volume with mostly zero errors"""
        error_counts = []
    
        # Select random days for catastrophic errors (0.5% of days)
        # Calculate the sample size, ensuring at least 1 day if any requests exist
        total_days = len(requests)
        if total_days > 0:
            sample_size = max(1, int(total_days * 0.005))
            # Ensure we don't try to sample more days than available
            sample_size = min(sample_size, total_days)
            catastrophic_days = set(random.sample(range(total_days), k=sample_size))
        else:
            catastrophic_days = set()
    
        # Select random days for elevated errors (2% of days)
        # Get available days (excluding catastrophic days)
        available_days = [i for i in range(len(requests)) if i not in catastrophic_days]

        # Calculate sample size for elevated errors
        if available_days:
            sample_size = max(1, int(len(available_days) * 0.02))
            # Ensure we don't try to sample more than available
            sample_size = min(sample_size, len(available_days))
            elevated_error_days = set(random.sample(available_days, k=sample_size))
        else:
            elevated_error_days = set()

        # Select random days for normal errors (10% of remaining days)
        available_days = [i for i in range(len(requests)) 
                 if i not in catastrophic_days and i not in elevated_error_days]        

        print(f"Total days: {len(requests)}")
        print(f"Catastrophic days: {len(catastrophic_days)}")
        print(f"Elevated error days: {len(elevated_error_days)}")
        print(f"Available days: {len(available_days)}")
        print(f"Trying to sample: {max(1, int(len(available_days) * 0.10))} days")
    

        # Add a check to ensure we have days to sample from
        if available_days:
            normal_error_days = set(random.sample(available_days, 
                                        k=max(1, int(len(available_days) * 0.10))))
        else:
            normal_error_days = set()  # or handle this case as needed
    
        for day, req_count in enumerate(requests):
            if day in catastrophic_days:
                # Catastrophic error day: 40-90% of requests fail
                error_rate = random.uniform(0.4, 0.9)
                errors = int(req_count * error_rate)
            
                # Add extra errors to simulate cascade failures
                cascade_errors = int(req_count * random.uniform(0.1, 0.3))
                errors += cascade_errors
            
            elif day in elevated_error_days:
                # Elevated error day: 10-30% of requests fail
                error_rate = random.uniform(0.1, 0.3)
                errors = int(req_count * error_rate)
            
            elif day in normal_error_days:
                # Normal error day: use base error rate with variation
                base_errors = int(req_count * base_error_rate)
                error_variation = np.random.normal(0, base_errors * 0.1)  # 10% standard deviation
                errors = int(base_errors + error_variation)
            
            else:
                # Most days (87.5% of days) have zero errors
                errors = 0
        
            error_counts.append(max(0, errors))
    
        return error_counts

def generate_project_requests(project_id: str, start_date: datetime, end_date: datetime, 
                            plan_type: str, pattern_type: str, error_frequency: str | None = None) -> Tuple[List[Dict], str]:
    """Generate daily requests for a project based on its behavior pattern"""
    
    # Base volumes per plan
    plan_volumes = {
        'free': 100,
        'base': 200,
        'advanced': 1000
    }
    
    # Error rates per plan
    error_rates = {
        'free': 0.1,
        'base': 0.05,
        'advanced': 0.02
    }
    

    generator = RequestPatternGenerator(start_date, end_date)
    base_volume = plan_volumes[plan_type]
    
    # Generate requests based on pattern type
    if pattern_type == 'silent':
        requests = generator.generate_silent_pattern(base_volume)
    elif pattern_type == 'increasing':
        requests = generator.generate_increasing_pattern(base_volume)
    elif pattern_type == 'intermittent':
        requests = generator.generate_intermittent_pattern(base_volume)
    elif pattern_type == 'decreasing': 
        requests = generator.generate_decreasing_pattern(base_volume)
    else:
        requests = generator.generate_steady_pattern(base_volume)
    
    
    # Generate corresponding error counts
    error_rate = error_rates[plan_type]
    if error_frequency == "low":
        error_rate = error_rate - 0.01
    elif error_frequency == 'high':
        error_rate = error_rate + 0.1
    else:
        pass
    
    errors = generator.generate_error_rates(requests, error_rate)
    
    # Create daily records
    daily_records = []
    current_date = start_date
    
    for req_count, error_count in zip(requests, errors):
        daily_records.append({
            'project_id': project_id,
            'date': current_date.date(),
            'request_count': req_count,
            'error_count': error_count,
            'error_rate': round(error_count / req_count * 100, 2) if req_count > 0 else 0
        })
        current_date += timedelta(days=1)
    
    return daily_records, pattern_type

# # Example usage:
# start_date = datetime(2023, 1, 1)
# end_date = datetime(2024, 1, 1)
# project_id = str(uuid.uuid4())
# sample_data, pattern = generate_project_requests(project_id, start_date, end_date, 'base')

# # Print days with high error rates
# print(f"Project type: {pattern}")
# print("\nDays with significant errors:")
# for day in sorted(sample_data, key=lambda x: x['error_rate'], reverse=True)[:5]:
#     print(f"Date: {day['date']}, Requests: {day['request_count']}, "
#           f"Errors: {day['error_count']}, Error Rate: {day['error_rate']}%")
    
# for day in sample_data:
#     print(f"Date: {day['date']}, Requests: {day['request_count']}, "
#           f"Errors: {day['error_count']}, Error Rate: {day['error_rate']}%")
    
    
class ProjectRequestGenerator:
    def __init__(self, connection_params: Dict):
        self.conn = psycopg2.connect(**connection_params)
        self.cursor = self.conn.cursor()
        
    def get_project_info(self, project_id: str) -> Dict:
        """Fetch project information including its current plan"""
        self.cursor.execute("""
            WITH latest_plan AS (
                SELECT plan_id
                FROM Project_Plan_Changelogs
                WHERE project_id = %s
                ORDER BY created_at DESC
                LIMIT 1
            )
            SELECT 
                p.id,
                p.created_at AT TIME ZONE 'UTC',
                pl.name as plan_name
            FROM Projects p
            JOIN latest_plan lp ON true
            JOIN Plans pl ON pl.id = lp.plan_id
            WHERE p.id = %s
        """, (project_id, project_id))
        
        result = self.cursor.fetchone()
        if not result:
            raise ValueError(f"Project {project_id} not found")
            
        return {
            'id': result[0],
            'created_at': result[1].replace(tzinfo=None),  # Make naive
            'plan_name': result[2]
        }
    
    def generate_and_insert_request_data(self, project_id: str, pattern_type, error_frequency: str | None = None, end_date: datetime | None = None):
        """Generate and insert request and error data for a project"""
        try:
            # Get project info
            project = self.get_project_info(project_id)
            
            # Set date range
            start_date = project['created_at']
            if end_date is None:
                end_date = datetime.now()
            else:
                # Ensure end_date is naive
                end_date = end_date.replace(tzinfo=None)
            
            # Generate request patterns
            daily_records, pattern_type = generate_project_requests(
                project_id,
                start_date,
                end_date,
                project['plan_name'],
                pattern_type,
                error_frequency
            )
            print(pattern_type)
            print()
            for day in daily_records:
                print(day)
            

            # Prepare data for insertion
            request_data = [
                (record['project_id'], record['date'], record['request_count'])
                for record in daily_records
            ]
            
            error_data = [
                (record['project_id'], record['date'], 
                 record['request_count'] - record['error_count'],  # success_count
                 record['error_count'],
                 record['error_rate'])
                for record in daily_records
            ]
            
            # Insert request data with update on conflict
            execute_values(
                self.cursor,
                """
                INSERT INTO Requests_Daily_Count (project_id, date, request_count)
                VALUES %s
                ON CONFLICT (project_id, date) 
                DO UPDATE SET request_count = EXCLUDED.request_count
                """,
                request_data,
                template="(%s, %s, %s)"
            )
            
            # Insert error data with update on conflict
            execute_values(
                self.cursor,
                """
                INSERT INTO Error_Rate_Daily 
                    (project_id, date, success_count, error_count, error_rate)
                VALUES %s
                ON CONFLICT (project_id, date)
                DO UPDATE SET 
                    success_count = EXCLUDED.success_count,
                    error_count = EXCLUDED.error_count,
                    error_rate = EXCLUDED.error_rate
                """,
                error_data,
                template="(%s, %s, %s, %s, %s)"
            )
            
            self.conn.commit()
            
            return {
                'project_id': project_id,
                'pattern_type': pattern_type,
                'date_range': f"{start_date.date()} to {end_date.date()}",
                'days_generated': len(daily_records),
                'total_requests': sum(record['request_count'] for record in daily_records),
                'total_errors': sum(record['error_count'] for record in daily_records),
                'avg_error_rate': round(sum(record['error_rate'] for record in daily_records) / len(daily_records), 2) if len(daily_records) > 0 else 0
            }
            
        except Exception as e:
            self.conn.rollback()
            raise e
    
    def close(self):
        """Close database connection"""
        self.cursor.close()
        self.conn.close()

def generate_and_insert_usage(connection_params: dict, project_id, request_pattern_type):
    try:
        # Initialize generator
        generator = ProjectRequestGenerator(connection_params)
        
        # Example: Generate data for a specific project
        result = generator.generate_and_insert_request_data(project_id, pattern_type=request_pattern_type)
        
        return result
    except Exception as e:
        print(f"Error occurred: {e}")
        raise
    finally:
        generator.close() # type: ignore

def main():
    # Database connection parameters
    connection_params = {
        'dbname': 'control_plane_new',
        'user': 'postgres',
        'password': 'postgres',
        'host': 'localhost',
        'port': '5432'
    }
    
    try:
        # Initialize generator
        generator = ProjectRequestGenerator(connection_params)
        
        # Example: Generate data for a specific project
        project_id = "9e0f8d60-3af5-48b2-9868-b73584df07e4"  # Replace with actual project ID
        result = generator.generate_and_insert_request_data(project_id, pattern_type="steady", error_frequency='high')
        
        print("Successfully generated and inserted request data:")
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        print(f"Error occurred: {e}")
        raise
    finally:
        generator.close() # type: ignore

if __name__ == "__main__":
    main()