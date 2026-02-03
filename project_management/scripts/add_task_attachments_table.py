"""
Add task_attachments table to store file attachments for tasks
Run this script to add the table to all tenant databases
"""

import pymysql
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Master DB connection config
MASTER_DB_CONFIG = {
    'db_host': os.environ.get('MYSQL_ADMIN_HOST', '127.0.0.1'),
    'db_port': int(os.environ.get('MYSQL_ADMIN_PORT') or 3306),
    'db_user': os.environ.get('MYSQL_ADMIN_USER', 'root'),
    'db_password': os.environ.get('MYSQL_ADMIN_PWD', 'root'),
    'db_name': os.environ.get('MASTER_DB_NAME', 'master_db')
}

def add_task_attachments_table():
    """Add task_attachments table to all tenant databases"""
    print("\n" + "="*70)
    print(" "*15 + "ADD TASK ATTACHMENTS TABLE")
    print("="*70)
    
    # Connect to master database
    print("\n🔌 Connecting to master database...")
    try:
        master_conn = pymysql.connect(
            host=MASTER_DB_CONFIG['db_host'],
            port=MASTER_DB_CONFIG['db_port'],
            user=MASTER_DB_CONFIG['db_user'],
            password=MASTER_DB_CONFIG['db_password'],
            database=MASTER_DB_CONFIG['db_name'],
            cursorclass=pymysql.cursors.DictCursor
        )
        print("✅ Connected to master database")
    except Exception as e:
        print(f"❌ Failed to connect to master database: {e}")
        return
    
    try:
        with master_conn.cursor() as cur:
            # Get all tenants
            cur.execute("SELECT id, client_name, db_name, db_host, db_user, db_password FROM clients_master")
            tenants = cur.fetchall()
            
            if not tenants:
                print("\n⚠️  No tenants found in master database")
                return
            
            print(f"\n📋 Found {len(tenants)} tenant(s)")
            print("-" * 70)
            
            success_count = 0
            error_count = 0
            
            for tenant in tenants:
                tenant_name = tenant['client_name'] or tenant['db_name']
                print(f"\n🔧 Processing tenant: {tenant_name}")
                
                try:
                    # Connect to tenant database
                    tenant_conn = pymysql.connect(
                        host=tenant['db_host'],
                        user=tenant['db_user'],
                        password=tenant['db_password'],
                        database=tenant['db_name'],
                        cursorclass=pymysql.cursors.DictCursor
                    )
                    
                    with tenant_conn.cursor() as tenant_cur:
                        # Check if table already exists
                        tenant_cur.execute("""
                            SELECT COUNT(*) as count 
                            FROM information_schema.tables 
                            WHERE table_schema = %s AND table_name = 'task_attachments'
                        """, (tenant['db_name'],))
                        
                        result = tenant_cur.fetchone()
                        
                        if result['count'] > 0:
                            print(f"   ⚠️  task_attachments table already exists - skipping")
                        else:
                            # Create task_attachments table
                            tenant_cur.execute("""
                                CREATE TABLE task_attachments (
                                    id INT AUTO_INCREMENT PRIMARY KEY,
                                    task_id INT NOT NULL,
                                    file_name VARCHAR(255) NOT NULL,
                                    file_path VARCHAR(512) NOT NULL,
                                    file_size INT,
                                    file_type VARCHAR(100),
                                    uploaded_by INT,
                                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                    INDEX idx_task_id (task_id),
                                    INDEX idx_uploaded_at (uploaded_at),
                                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                                    FOREIGN KEY (uploaded_by) REFERENCES members(id) ON DELETE SET NULL
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                            """)
                            
                            tenant_conn.commit()
                            print(f"   ✅ task_attachments table created successfully")
                            success_count += 1
                    
                    tenant_conn.close()
                    
                except Exception as e:
                    print(f"   ❌ Error processing tenant {tenant_name}: {e}")
                    error_count += 1
            
            print("\n" + "="*70)
            print("📊 SUMMARY")
            print("="*70)
            print(f"✅ Successfully processed: {success_count} tenant(s)")
            if error_count > 0:
                print(f"❌ Errors: {error_count} tenant(s)")
            print("")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        master_conn.close()

if __name__ == "__main__":
    add_task_attachments_table()
