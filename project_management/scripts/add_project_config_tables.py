"""
Script to add project configuration tables for work types and statuses.
This allows organizations to configure their project workflows similar to Jira.
"""
import pymysql
import sys
import os
from django.conf import settings
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
django.setup()

from django.db import connection as default_connection

def add_config_tables_to_tenant(db_config):
    """Add configuration tables to a tenant database"""
    conn = pymysql.connect(
        host=db_config.get('db_host', '127.0.0.1'),
        port=int(db_config.get('db_port', 3306)),
        user=db_config.get('db_user'),
        password=db_config.get('db_password'),
        database=db_config.get('db_name'),
        cursorclass=pymysql.cursors.DictCursor
    )
    cur = conn.cursor()
    
    try:
        # Table 1: Project Work Types Configuration
        cur.execute("""
            CREATE TABLE IF NOT EXISTS project_work_types (
                id INT AUTO_INCREMENT PRIMARY KEY,
                project_id INT NOT NULL,
                work_type VARCHAR(50) NOT NULL,
                is_enabled BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        
        # Table 2: Project Statuses Configuration
        cur.execute("""
            CREATE TABLE IF NOT EXISTS project_statuses (
                id INT AUTO_INCREMENT PRIMARY KEY,
                project_id INT NOT NULL,
                status_name VARCHAR(100) NOT NULL,
                status_order INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        
        # Add work_type column to tasks table if not exists
        cur.execute("""
            SELECT COUNT(*) as cnt FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'tasks' AND COLUMN_NAME = 'work_type'
        """, (db_config['db_name'],))
        result = cur.fetchone()
        
        if result['cnt'] == 0:
            cur.execute("""
                ALTER TABLE tasks ADD COLUMN work_type VARCHAR(50) DEFAULT 'Task'
            """)
            print(f"  ✓ Added work_type column to tasks table")
        else:
            print(f"  ℹ work_type column already exists in tasks table")
        
        conn.commit()
        print(f"  ✓ Successfully added project configuration tables")
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def main():
    # Get all tenants from Django default DB
    with default_connection.cursor() as cur:
        cur.execute("SELECT * FROM clients_master")
        columns = [col[0] for col in cur.description]
        tenants = [dict(zip(columns, row)) for row in cur.fetchall()]
    
    if not tenants:
        print("No tenants found in clients_master table")
        return
    
    print(f"Found {len(tenants)} tenant(s). Adding project configuration tables...\n")
    
    for tenant in tenants:
        org_name = tenant.get('org_name', 'Unknown')
        print(f"Processing tenant: {org_name}")
        
        db_config = {
            'db_host': tenant.get('db_host'),
            'db_port': tenant.get('db_port', 3306),
            'db_user': tenant.get('db_user'),
            'db_password': tenant.get('db_password'),
            'db_name': tenant.get('db_name')
        }
        
        try:
            add_config_tables_to_tenant(db_config)
        except Exception as e:
            print(f"  ✗ Failed to process tenant {org_name}: {e}")
    
    print("\n✅ Migration complete!")

if __name__ == '__main__':
    main()
