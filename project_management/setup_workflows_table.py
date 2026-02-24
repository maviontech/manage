#!/usr/bin/env python
"""
Setup workflows table in tenant database
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from core.db_helpers import get_tenant_conn
from django.test import RequestFactory

def setup_workflows_table():
    """Create workflows table and add sample data"""
    
    # Create a mock request with session data
    factory = RequestFactory()
    request = factory.get('/')
    
    # You'll need to set your tenant credentials here
    request.session = {
        'tenant_db_name': 'your_tenant_db',  # Change this
        'tenant_db_user': 'your_user',        # Change this
        'tenant_db_password': 'your_password', # Change this
        'tenant_db_host': '127.0.0.1',
        'tenant_db_port': 3306
    }
    
    try:
        conn = get_tenant_conn(request)
        cur = conn.cursor()
        
        # Create workflows table
        print("Creating workflows table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                status ENUM('Active', 'Draft', 'Archived') DEFAULT 'Draft',
                created_by INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_status (status),
                INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        print("✓ Workflows table created")
        
        # Check if sample data already exists
        cur.execute("SELECT COUNT(*) as cnt FROM workflows")
        result = cur.fetchone()
        count = result['cnt'] if isinstance(result, dict) else result[0]
        
        if count == 0:
            print("Adding sample workflows...")
            sample_workflows = [
                ('Development Workflow', 'Standard development process from planning to deployment', 'Active'),
                ('Bug Fix Workflow', 'Quick workflow for addressing and resolving bugs', 'Active'),
                ('Feature Request Workflow', 'Process for evaluating and implementing new features', 'Draft'),
                ('Code Review Workflow', 'Peer review process for code quality assurance', 'Active'),
                ('Release Workflow', 'Steps for preparing and deploying releases', 'Draft'),
            ]
            
            for name, description, status in sample_workflows:
                cur.execute("""
                    INSERT INTO workflows (name, description, status)
                    VALUES (%s, %s, %s)
                """, (name, description, status))
            
            print(f"✓ Added {len(sample_workflows)} sample workflows")
        else:
            print(f"✓ Workflows table already has {count} records")
        
        conn.commit()
        cur.close()
        conn.close()
        
        print("\n✓ Setup complete!")
        print("Refresh your browser to see the workflows.")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    print("=" * 60)
    print("Workflows Table Setup")
    print("=" * 60)
    print("\nIMPORTANT: Edit this script and set your tenant database credentials")
    print("in the request.session dictionary before running.\n")
    
    response = input("Have you updated the credentials? (yes/no): ")
    if response.lower() == 'yes':
        setup_workflows_table()
    else:
        print("\nPlease edit setup_workflows_table.py and update:")
        print("  - tenant_db_name")
        print("  - tenant_db_user")
        print("  - tenant_db_password")
        print("\nThen run this script again.")
