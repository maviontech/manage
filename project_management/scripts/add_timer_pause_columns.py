"""
Script to add pause/resume columns to timer_sessions table in all tenant databases
Run this to enable timer pause functionality
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

def add_timer_pause_columns():
    """Add pause/resume columns to timer_sessions table in all tenant databases"""
    
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
        
        print(f"✅ Connected to master database: {MASTER_DB}")
        
        master_cursor = master_conn.cursor()
        
        # Get all tenant databases
        master_cursor.execute("""
            SELECT id, client_name, db_name, db_host, db_user, db_password 
            FROM clients_master 
            WHERE is_active = 1
            ORDER BY client_name
        """)
        
        tenants = master_cursor.fetchall()
        
        if not tenants:
            print("\n⚠️ No active tenants found in master database")
            return
        
        print(f"\n📋 Found {len(tenants)} active tenant(s)")
        print("="*70)
        
        success_count = 0
        error_count = 0
        skip_count = 0
        
        for tenant in tenants:
            tenant_id = tenant['id']
            client_name = tenant['client_name']
            db_name = tenant['db_name']
            db_host = tenant['db_host']
            db_user = tenant['db_user']
            db_password = tenant['db_password']
            
            print(f"\n🔄 Processing tenant: {client_name} (ID: {tenant_id})")
            print(f"   Database: {db_name} @ {db_host}")
            
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
                
                # Check if timer_sessions table exists
                tenant_cursor.execute("""
                    SELECT COUNT(*) as count 
                    FROM information_schema.tables 
                    WHERE table_schema = %s AND table_name = 'timer_sessions'
                """, (db_name,))
                
                result = tenant_cursor.fetchone()
                
                if result['count'] == 0:
                    print(f"   ⚠️ timer_sessions table doesn't exist - skipping")
                    skip_count += 1
                    tenant_cursor.close()
                    tenant_conn.close()
                    continue
                
                # Check if columns already exist
                tenant_cursor.execute("""
                    SELECT COUNT(*) as count 
                    FROM information_schema.columns 
                    WHERE table_schema = %s 
                    AND table_name = 'timer_sessions' 
                    AND column_name IN ('paused', 'paused_at', 'paused_duration')
                """, (db_name,))
                
                existing_cols = tenant_cursor.fetchone()['count']
                
                if existing_cols > 0:
                    print(f"   ✅ Pause columns already exist - skipping")
                    skip_count += 1
                    tenant_cursor.close()
                    tenant_conn.close()
                    continue
                
                # Add pause columns
                print("   ➕ Adding pause columns...")
                
                # Add 'paused' column
                tenant_cursor.execute("""
                    ALTER TABLE timer_sessions 
                    ADD COLUMN paused TINYINT(1) DEFAULT 0 
                    AFTER is_running
                """)
                
                # Add 'paused_at' column
                tenant_cursor.execute("""
                    ALTER TABLE timer_sessions 
                    ADD COLUMN paused_at DATETIME NULL 
                    AFTER paused
                """)
                
                # Add 'paused_duration' column (in milliseconds)
                tenant_cursor.execute("""
                    ALTER TABLE timer_sessions 
                    ADD COLUMN paused_duration INT DEFAULT 0 
                    AFTER paused_at
                """)
                
                tenant_conn.commit()
                
                print(f"   ✅ Successfully added pause columns to {client_name}")
                success_count += 1
                
                tenant_cursor.close()
                tenant_conn.close()
                
            except pymysql.Error as e:
                print(f"   ❌ Database error for {client_name}: {e}")
                error_count += 1
                try:
                    tenant_conn.rollback()
                    tenant_cursor.close()
                    tenant_conn.close()
                except:
                    pass
            except Exception as e:
                print(f"   ❌ Unexpected error for {client_name}: {e}")
                error_count += 1
        
        master_cursor.close()
        master_conn.close()
        
        # Print summary
        print("\n" + "="*70)
        print("📊 MIGRATION SUMMARY")
        print("="*70)
        print(f"✅ Successfully updated: {success_count} tenant(s)")
        print(f"⚠️ Skipped: {skip_count} tenant(s)")
        print(f"❌ Errors: {error_count} tenant(s)")
        print("="*70)
        
        if success_count > 0:
            print("\n✨ Timer pause functionality is now enabled!")
            print("💡 Users can now pause and resume their timers.")
        
    except pymysql.Error as e:
        print(f"\n❌ Master database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    print("\n" + "="*70)
    print(" "*15 + "ADD TIMER PAUSE COLUMNS MIGRATION")
    print("="*70)
    print("\n⚙️  Configuration:")
    print(f"   Master DB: {MASTER_DB}")
    print(f"   Host: {ADMIN_HOST}:{ADMIN_PORT}")
    print(f"   User: {ADMIN_USER}")
    print("="*70)
    
    input("\n⏸️  Press Enter to continue or Ctrl+C to cancel...")
    
    add_timer_pause_columns()
