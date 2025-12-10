"""
Script to add timer_sessions table to all existing tenant databases
Run this after adding the timer feature to update existing tenants
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

def add_timer_sessions_table():
    """Add timer_sessions table to all tenant databases"""
    
    # Timer sessions table DDL
    TIMER_SESSIONS_DDL = """
    CREATE TABLE IF NOT EXISTS timer_sessions (
      id INT AUTO_INCREMENT PRIMARY KEY,
      user_id INT NOT NULL,
      task_id INT,
      start_time DATETIME NOT NULL,
      end_time DATETIME,
      duration_seconds INT DEFAULT 0,
      is_running TINYINT(1) DEFAULT 1,
      notes TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      FOREIGN KEY (user_id) REFERENCES members(id) ON DELETE CASCADE,
      FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL,
      INDEX idx_user_id (user_id),
      INDEX idx_task_id (task_id),
      INDEX idx_is_running (is_running)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    
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
                
                # Create timer_sessions table
                tenant_cursor.execute(TIMER_SESSIONS_DDL)
                tenant_conn.commit()
                
                print(f"✅ Added timer_sessions table to tenant: {db_name}")
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
    print("Adding timer_sessions table to tenant databases")
    print("=" * 60)
    print()
    
    add_timer_sessions_table()
    
    print()
    print("=" * 60)
    print("Done!")
    print("=" * 60)
