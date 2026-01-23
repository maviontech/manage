"""
Script to add system information columns to tasks table.
Captures browser, OS, screen resolution, and timestamp for debugging.
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

def add_system_info_columns(db_config):
    """Add system info columns to tasks table in a tenant database"""
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
        # Add browser column
        cur.execute("""
            SELECT COUNT(*) as cnt FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'tasks' AND COLUMN_NAME = 'si_browser'
        """, (db_config['db_name'],))
        result = cur.fetchone()
        
        if result['cnt'] == 0:
            cur.execute("""
                ALTER TABLE tasks ADD COLUMN si_browser VARCHAR(255) DEFAULT NULL AFTER work_type
            """)
            print(f"  ✓ Added si_browser column to tasks table")
        else:
            print(f"  ℹ si_browser column already exists")
        
        # Add screen resolution column
        cur.execute("""
            SELECT COUNT(*) as cnt FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'tasks' AND COLUMN_NAME = 'si_resolution'
        """, (db_config['db_name'],))
        result = cur.fetchone()
        
        if result['cnt'] == 0:
            cur.execute("""
                ALTER TABLE tasks ADD COLUMN si_resolution VARCHAR(50) DEFAULT NULL AFTER si_browser
            """)
            print(f"  ✓ Added si_resolution column to tasks table")
        else:
            print(f"  ℹ si_resolution column already exists")
        
        # Add operating system column
        cur.execute("""
            SELECT COUNT(*) as cnt FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'tasks' AND COLUMN_NAME = 'si_os'
        """, (db_config['db_name'],))
        result = cur.fetchone()
        
        if result['cnt'] == 0:
            cur.execute("""
                ALTER TABLE tasks ADD COLUMN si_os VARCHAR(100) DEFAULT NULL AFTER si_resolution
            """)
            print(f"  ✓ Added si_os column to tasks table")
        else:
            print(f"  ℹ si_os column already exists")
        
        # Add timestamp column
        cur.execute("""
            SELECT COUNT(*) as cnt FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'tasks' AND COLUMN_NAME = 'si_timestamp'
        """, (db_config['db_name'],))
        result = cur.fetchone()
        
        if result['cnt'] == 0:
            cur.execute("""
                ALTER TABLE tasks ADD COLUMN si_timestamp VARCHAR(50) DEFAULT NULL AFTER si_os
            """)
            print(f"  ✓ Added si_timestamp column to tasks table")
        else:
            print(f"  ℹ si_timestamp column already exists")
        
        conn.commit()
        print(f"  ✓ Successfully added system info columns to tasks table")
        
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
    
    print(f"Found {len(tenants)} tenant(s). Adding system info columns...\n")
    
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
        
        add_system_info_columns(db_config)
        print()
    
    print("✓ All tenants processed successfully!")

if __name__ == '__main__':
    main()
