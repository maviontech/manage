"""
Script to add notifications table to all existing tenant databases
Run this after adding the notifications feature to update existing tenants
"""

import os
import sys
import pymysql

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db_connector import get_master_connection

def add_notifications_table():
    """Add notifications table to all tenant databases"""
    
    # Notifications table DDL
    NOTIFICATIONS_DDL = """
    CREATE TABLE IF NOT EXISTS notifications (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        title VARCHAR(255) NOT NULL,
        message TEXT,
        type ENUM('info', 'success', 'warning', 'error', 'task', 'project', 'team') DEFAULT 'info',
        is_read BOOLEAN DEFAULT FALSE,
        link VARCHAR(512),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_user_id (user_id),
        INDEX idx_is_read (is_read),
        INDEX idx_created_at (created_at),
        FOREIGN KEY (user_id) REFERENCES members(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """
    
    try:
        # Get master database connection
        master_conn = get_master_connection()
        if not master_conn:
            print("❌ Failed to connect to master database")
            return
        
        master_cursor = master_conn.cursor(pymysql.cursors.DictCursor)
        
        # Get all tenants
        master_cursor.execute("SELECT tenant_id, db_name FROM tenants")
        tenants = master_cursor.fetchall()
        
        if not tenants:
            print("⚠️  No tenants found in master database")
            master_conn.close()
            return
        
        print(f"\n📋 Found {len(tenants)} tenant(s)")
        print("=" * 60)
        
        success_count = 0
        error_count = 0
        
        for tenant in tenants:
            tenant_id = tenant['tenant_id']
            db_name = tenant['db_name']
            
            try:
                print(f"\n🔧 Processing tenant: {tenant_id} (DB: {db_name})")
                
                # Connect to tenant database
                tenant_conn = pymysql.connect(
                    host='localhost',
                    user='root',
                    password='',
                    database=db_name,
                    charset='utf8mb4',
                    cursorclass=pymysql.cursors.DictCursor
                )
                
                tenant_cursor = tenant_conn.cursor()
                
                # Check if table already exists
                tenant_cursor.execute("""
                    SELECT COUNT(*) as count 
                    FROM information_schema.tables 
                    WHERE table_schema = %s AND table_name = 'notifications'
                """, (db_name,))
                
                result = tenant_cursor.fetchone()
                
                if result['count'] > 0:
                    print(f"   ℹ️  notifications table already exists, skipping...")
                else:
                    # Create notifications table
                    tenant_cursor.execute(NOTIFICATIONS_DDL)
                    tenant_conn.commit()
                    print(f"   ✅ notifications table created successfully")
                
                tenant_conn.close()
                success_count += 1
                
            except Exception as e:
                print(f"   ❌ Error: {str(e)}")
                error_count += 1
                continue
        
        master_conn.close()
        
        print("\n" + "=" * 60)
        print(f"\n📊 Summary:")
        print(f"   ✅ Successful: {success_count}")
        print(f"   ❌ Errors: {error_count}")
        print(f"   📝 Total: {len(tenants)}")
        print("\n✨ Migration completed!\n")
        
    except Exception as e:
        print(f"\n❌ Fatal error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🔔 NOTIFICATIONS TABLE MIGRATION")
    print("=" * 60)
    print("\nThis script will add the notifications table to all tenant databases.")
    print("\nPress Ctrl+C to cancel, or Enter to continue...")
    
    try:
        input()
        add_notifications_table()
    except KeyboardInterrupt:
        print("\n\n❌ Migration cancelled by user\n")
