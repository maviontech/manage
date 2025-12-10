"""
Script to update time_entries table with new columns for approval workflow
Run this to add description, status, approved_by, approved_at, and updated_at columns
"""

import os
import sys
import pymysql

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Get MySQL admin credentials from environment or prompt
MASTER_DB = os.environ.get('MASTER_DB_NAME', 'master_db')
ADMIN_HOST = os.environ.get('MYSQL_ADMIN_HOST', '127.0.0.1')
ADMIN_PORT = int(os.environ.get('MYSQL_ADMIN_PORT', 3306))
ADMIN_USER = os.environ.get('MYSQL_ADMIN_USER', 'root')
ADMIN_PWD = os.environ.get('MYSQL_ADMIN_PWD', 'root')

def update_time_entries_table():
    """Update time_entries table with new columns for approval workflow"""
    
    # SQL statements to add new columns (without IF NOT EXISTS)
    ALTER_STATEMENTS = [
        "ALTER TABLE time_entries ADD COLUMN description TEXT AFTER date",
        "ALTER TABLE time_entries ADD COLUMN status ENUM('pending', 'approved', 'rejected') DEFAULT 'pending' AFTER description",
        "ALTER TABLE time_entries ADD COLUMN approved_by INT AFTER status",
        "ALTER TABLE time_entries ADD COLUMN approved_at TIMESTAMP NULL AFTER approved_by",
        "ALTER TABLE time_entries ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER approved_at",
    ]
    
    # Add foreign keys and indexes
    CONSTRAINT_STATEMENTS = [
        """
        ALTER TABLE time_entries 
        ADD CONSTRAINT fk_te_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
        """,
        """
        ALTER TABLE time_entries 
        ADD CONSTRAINT fk_te_user FOREIGN KEY (user_id) REFERENCES members(id) ON DELETE CASCADE
        """,
        """
        ALTER TABLE time_entries 
        ADD CONSTRAINT fk_te_approver FOREIGN KEY (approved_by) REFERENCES members(id) ON DELETE SET NULL
        """,
        "CREATE INDEX idx_te_user_id ON time_entries(user_id)",
        "CREATE INDEX idx_te_task_id ON time_entries(task_id)",
        "CREATE INDEX idx_te_status ON time_entries(status)",
        "CREATE INDEX idx_te_date ON time_entries(date)",
    ]
    
    try:
        # Connect to master database
        master_conn = pymysql.connect(
            host=ADMIN_HOST,
            port=ADMIN_PORT,
            user=ADMIN_USER,
            password=ADMIN_PWD,
            database=MASTER_DB,
            cursorclass=pymysql.cursors.DictCursor
        )
        
        if not master_conn:
            print("❌ Failed to connect to master database")
            return
        
        master_cursor = master_conn.cursor()
        
        # Get all tenants
        master_cursor.execute("SELECT * FROM clients_master WHERE db_engine='mysql'")
        tenants = master_cursor.fetchall()
        
        if not tenants:
            print("⚠️  No tenants found in master database")
            master_cursor.close()
            master_conn.close()
            return
        
        print(f"📋 Found {len(tenants)} tenant(s)")
        print()
        
        # Process each tenant
        success_count = 0
        for tenant in tenants:
            tenant_id = tenant.get('id')
            db_name = tenant.get('db_name')
            db_user = tenant.get('db_user')
            db_password = tenant.get('db_password')
            db_host = tenant.get('db_host', '127.0.0.1')
            db_port = tenant.get('db_port', 3306)
            
            if not all([db_name, db_user, db_password]):
                print(f"⚠️  Skipping tenant {tenant_id}: Missing database credentials")
                continue
            
            try:
                # Connect to tenant database
                tenant_conn = pymysql.connect(
                    host=db_host,
                    port=db_port,
                    user=db_user,
                    password=db_password,
                    database=db_name,
                    cursorclass=pymysql.cursors.DictCursor
                )
                
                tenant_cursor = tenant_conn.cursor()
                
                print(f"🔧 Updating time_entries table in {db_name}...")
                
                # Add new columns
                for stmt in ALTER_STATEMENTS:
                    try:
                        tenant_cursor.execute(stmt)
                    except pymysql.err.OperationalError as e:
                        # Column might already exist, check error
                        if "Duplicate column name" in str(e):
                            print(f"   ℹ️  Column already exists, skipping...")
                        else:
                            print(f"   ⚠️  Warning: {str(e)}")
                
                tenant_conn.commit()
                
                # Add foreign keys and indexes (with error handling)
                for stmt in CONSTRAINT_STATEMENTS:
                    try:
                        tenant_cursor.execute(stmt)
                        tenant_conn.commit()
                    except pymysql.err.OperationalError as e:
                        # Constraint might already exist
                        if "Duplicate key name" in str(e) or "already exists" in str(e):
                            pass  # Ignore duplicate constraint errors
                        else:
                            print(f"   ⚠️  Warning: {str(e)}")
                    except Exception as e:
                        print(f"   ⚠️  Warning: {str(e)}")
                
                print(f"✅ Successfully updated time_entries table in {db_name}")
                success_count += 1
                
                tenant_cursor.close()
                tenant_conn.close()
                
            except Exception as e:
                print(f"❌ Error processing tenant {db_name}: {str(e)}")
                continue
        
        master_cursor.close()
        master_conn.close()
        
        print()
        print(f"🎉 Successfully updated {success_count} out of {len(tenants)} tenant(s)")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 60)
    print("Updating time_entries table with approval workflow columns")
    print("=" * 60)
    print()
    
    update_time_entries_table()
    
    print()
    print("=" * 60)
    print("Done!")
    print("=" * 60)
