from datetime import datetime, timedelta, date
import uuid
import random
from typing import List, Dict, Optional, Tuple
import psycopg2
from psycopg2.extras import execute_values
from decimal import Decimal

class ProjectInvoiceGenerator:
    def __init__(self, connection_params: Dict):
        self.conn = psycopg2.connect(**connection_params)
        self.cursor = self.conn.cursor()
    
    def get_project_info(self, project_id: str) -> Dict:
        """Get project and customer information"""
        self.cursor.execute("""
            SELECT 
                p.id,
                p.active_models,
                p.created_at,
                p.deleted_at,
                u.customer_id
            FROM Projects p
            JOIN Users u ON p.owner_id = u.id
            WHERE p.id = %s
        """, (project_id,))
        
        row = self.cursor.fetchone()
        if not row:
            raise ValueError(f"Project {project_id} not found")
            
        return {
            'id': str(row[0]),
            'active_models': row[1],
            'created_at': row[2],
            'deleted_at': row[3],
            'customer_id': row[4]
        }
    
    def get_project_plan(self, project_id: str, month: int, year: int) -> Optional[Dict]:
        """Get the active plan for a project in a given month"""
        month_start = date(year, month, 1)
        month_end = date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1)
        
        self.cursor.execute("""
            WITH ordered_changes AS (
                SELECT 
                    pc.created_at,
                    pl.name as plan_name,
                    LEAD(pc.created_at) OVER (ORDER BY pc.created_at) as next_change_date
                FROM Project_Plan_Changelogs pc
                JOIN Plans pl ON pl.id = pc.plan_id
                WHERE pc.project_id = %s
                AND pc.created_at <= %s
                ORDER BY pc.created_at DESC
                LIMIT 1
            )
            SELECT * FROM ordered_changes
        """, (project_id, month_end))
        
        row = self.cursor.fetchone()
        if not row:
            return None
            
        return {
            'start_date': row[0].date(),
            'plan_name': row[1],
            'end_date': row[2].date() if row[2] else None
        }
    
    def calculate_amount(self, active_models: int, plan_name: str, price_per_model: int) -> Decimal:
        """Calculate invoice amount based on plan and active models"""
        if plan_name == 'base':
            return Decimal(str(active_models * 5.0)).quantize(Decimal('0.00'))  # $5 per active model
        elif plan_name == 'advanced':

            return Decimal(str(active_models * price_per_model)).quantize(Decimal('0.00'))
        return Decimal('0')
    
    def generate_invoice_id(self, customer_id: str, month: int, year: int) -> str:
        """Generate a unique invoice ID"""
        unique_id = str(uuid.uuid4())
        return f"inv_{unique_id}_{month}_{year}"
    
    def generate_project_invoice(self, project_id: str, month: int, year: int, price_per_model) -> Optional[Tuple[Dict, Dict]]:
        """Generate invoice and invoice item for a project in a given month"""
        try:
            # Get project info
            project = self.get_project_info(project_id)
            
            # Check if project was active in this month
            month_start = date(year, month, 1)
            if (project['created_at'].date() > month_start or 
                (project['deleted_at'] and project['deleted_at'].date() < month_start)):
                return None
            
            # Get active plan for the month
            plan = self.get_project_plan(project_id, month, year)
            if not plan or plan['plan_name'] == 'free':
                return None
            
            # Generate invoice timestamp
            invoice_date = datetime(year, month, 26, 9, 0, 41, 625067)
            
            # Calculate amount
            amount = self.calculate_amount(project['active_models'], plan['plan_name'], price_per_model)
            if amount == 0:
                return None
            
            # Create invoice
            invoice_id = self.generate_invoice_id(project['customer_id'], month, year)
            invoice = {
                'stripe_invoice_id': invoice_id,
                'customer_id': project['customer_id'],
                'subscription_id': None,
                'month': month,
                'year': year,
                'description': '',
                'status': 'paid',
                'invoice_url': None,
                'attempt_count': None,
                'created_at': invoice_date,
                'updated_at': invoice_date
            }
            
            # Create invoice item
            invoice_item = {
                'id': str(uuid.uuid4()),
                'invoice_id': invoice_id,
                'amount': amount,
                'description': '',
                'project_id': project_id,
                'type': 'active-model-count',
                'month': month,
                'year': year,
                'has_updated_to_stripe': True,
                'error': None,
                'created_at': invoice_date,
                'updated_at': invoice_date
            }
            
            return invoice, invoice_item
            
        except Exception as e:
            self.conn.rollback()
            raise e
    
    def generate_all_invoices(self, project_id: str, price_per_model_advanced: int) -> List[Dict]:
        """Generate all invoices from project creation to current date"""
        try:
            # Get project info
            project = self.get_project_info(project_id)
            
            # Get date ranges
            start_date = project['created_at'].date()
            end_date = project['deleted_at'].date() if project['deleted_at'] else date.today()
            
            results = []
            current_date = start_date
            
            print('current_date: ', current_date)
            print('end_date: ', end_date)
            
            # Generate invoices for each month
            while current_date <= end_date:
                month = current_date.month
                year = current_date.year
                
                result = self.generate_project_invoice(project_id, month, year, price_per_model_advanced)
                if result:
                    invoice, invoice_item = result
                    
                    # Insert invoice
                    self.cursor.execute("""
                        INSERT INTO Invoice (
                            stripe_invoice_id, customer_id, subscription_id, month, year,
                            description, status, invoice_url, attempt_count,
                            created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (stripe_invoice_id) 
                        DO UPDATE SET
                            status = EXCLUDED.status,
                            updated_at = EXCLUDED.updated_at
                        RETURNING stripe_invoice_id
                    """, (
                        invoice['stripe_invoice_id'], invoice['customer_id'],
                        invoice['subscription_id'], invoice['month'], invoice['year'],
                        invoice['description'], invoice['status'], invoice['invoice_url'],
                        invoice['attempt_count'], invoice['created_at'], invoice['updated_at']
                    ))
                    
                    # Insert invoice item
                    self.cursor.execute("""
                        INSERT INTO Invoice_item (
                            id, invoice_id, amount, description, project_id, type,
                            month, year, has_updated_to_stripe, error,
                            created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) 
                        DO UPDATE SET
                            amount = EXCLUDED.amount,
                            updated_at = EXCLUDED.updated_at
                        RETURNING id
                    """, (
                        invoice_item['id'], invoice_item['invoice_id'],
                        invoice_item['amount'], invoice_item['description'],
                        invoice_item['project_id'], invoice_item['type'],
                        invoice_item['month'], invoice_item['year'],
                        invoice_item['has_updated_to_stripe'], invoice_item['error'],
                        invoice_item['created_at'], invoice_item['updated_at']
                    ))
                    
                    results.append({
                        'month': month,
                        'year': year,
                        'invoice_id': invoice['stripe_invoice_id'],
                        'amount': invoice_item['amount']
                    })
                
                # Move to next month
                if month == 12:
                    current_date = date(year + 1, 1, 1)
                else:
                    current_date = date(year, month + 1, 1)
            
            self.conn.commit()
            return results
            
        except Exception as e:
            self.conn.rollback()
            raise e
    
    def close(self):
        """Close database connection"""
        self.cursor.close()
        self.conn.close()

def generate_and_insert_invoices(connection_params, project_id, price_per_model_advanced):
    try:
        generator = ProjectInvoiceGenerator(connection_params)
        
        results = generator.generate_all_invoices(project_id, price_per_model_advanced=price_per_model_advanced)
        
        print(f"Generated invoices for project {project_id}:")
        print(f"Total invoices generated: {len(results)}")
        total_amount = sum(Decimal(str(r['amount'])) for r in results)
        print(f"Total amount: ${total_amount:.2f}")
        return results
        
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
        generator = ProjectInvoiceGenerator(connection_params)
        
        # Example usage for a specific project
        project_id = "a1596b61-18ce-4f7e-a516-9e67e5175738"  # Replace with actual project ID
        
        results = generator.generate_all_invoices(project_id, price_per_model_advanced=60)
        
        print(f"Generated invoices for project {project_id}:")
        print(f"Total invoices generated: {len(results)}")
        total_amount = sum(Decimal(str(r['amount'])) for r in results)
        print(f"Total amount: ${total_amount:.2f}")
        
        for result in results:
            print(f"\nMonth: {result['month']}/{result['year']}")
            print(f"Invoice ID: {result['invoice_id']}")
            print(f"Amount: ${result['amount']:.2f}")
        
    except Exception as e:
        print(f"Error occurred: {e}")
        raise
    finally:
        generator.close() # type: ignore

if __name__ == "__main__":
    main()