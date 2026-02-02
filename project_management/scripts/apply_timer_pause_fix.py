"""
Quick fix: Add pause columns to timer_sessions table
"""
import os
import sys
import pymysql

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MASTER_DB = os.environ.get('MASTER_DB_NAME', 'master_db')
ADMIN_HOST = os.environ.get('MYSQL_ADMIN_HOST', '127.0.0.1')
ADMIN_PORT = int(os.environ.get('MYSQL_ADMIN_PORT', 3306))
ADMIN_USER = os.environ.get('MYSQL_ADMIN_USER', 'root')
ADMIN_PWD = os.environ.get('MYSQL_ADMIN_PWD', 'root')

def fix_timer_pause():
    """Add pause columns to timer_sessions table"""
    
    try:
        # Connect to master database
        master_conn = pymysql.connect(
            host=ADMIN_HOST,
            port=ADMIN_PORT,
            user=ADMIN_USER,
            password=ADMIN_PWD,
            database=MASTER_DB,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False
        )
        
        print(f"✅ Connected to master database")
        
        master_cursor = master_conn.cursor()
        
        # Get all tenant databases
        master_cursor.execute("""
            SELECT db_name, db_host, db_user, db_password 
            FROM clients_master
        """)
        
        tenants = master_cursor.fetchall()
        
        print(f"📋 Found {len(tenants)} active tenant(s)")
        
        for tenant in tenants:
            db_name = tenant['db_name']
            db_host = tenant['db_host']
            db_user = tenant['db_user']
            db_password = tenant['db_password']
            
            print(f"\n🔄 Processing: {db_name}")
            
            try:
                # Connect to tenant database
                tenant_conn = pymysql.connect(
                    host=db_host,
                    port=3306,
                    user=db_user,
                    password=db_password,
                    database=db_name,
                    cursorclass=pymysql.cursors.DictCursor,
                    autocommit=False
                )
                
                tenant_cursor = tenant_conn.cursor()
                
                # Check if columns exist
                tenant_cursor.execute("""
                    SELECT COUNT(*) as count 
                    FROM information_schema.columns 
                    WHERE table_schema = %s 
                    AND table_name = 'timer_sessions' 
                    AND column_name = 'paused'
                """, (db_name,))
                
                if tenant_cursor.fetchone()['count'] > 0:
                    print(f"   ✅ Already has pause columns - skipping")
                    tenant_cursor.close()
                    tenant_conn.close()
                    continue
                
                # Add columns
                print("   ➕ Adding pause columns...")
                
                tenant_cursor.execute("""
                    ALTER TABLE timer_sessions 
                    ADD COLUMN paused TINYINT(1) DEFAULT 0 AFTER is_running,
                    ADD COLUMN paused_at DATETIME NULL AFTER paused,
                    ADD COLUMN paused_duration INT DEFAULT 0 AFTER paused_at
                """)
                
                tenant_conn.commit()
                print(f"   ✅ Successfully updated!")
                
                tenant_cursor.close()
                tenant_conn.close()
                
            except Exception as e:
                print(f"   ❌ Error: {e}")
                try:
                    tenant_conn.rollback()
                except:
                    pass
        
        master_cursor.close()
        master_conn.close()
        
        print("\n✨ Migration complete!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    fix_timer_pause()
