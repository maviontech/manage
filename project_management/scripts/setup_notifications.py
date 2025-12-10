"""
Quick script to add notifications table to current tenant database
"""

import pymysql
import sys

# Database connection details
DB_HOST = 'localhost'
DB_USER = 'root'
DB_PASSWORD = ''

print("\n" + "="*60)
print("NOTIFICATIONS TABLE SETUP")
print("="*60)

# Ask for database name
db_name = input("\nEnter your tenant database name (e.g., mavion_db): ").strip()

if not db_name:
    print("❌ Database name is required!")
    sys.exit(1)

print(f"\n📋 Connecting to database: {db_name}")

try:
    # Connect to the database
    conn = pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=db_name,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    
    cursor = conn.cursor()
    
    # Check if table already exists
    cursor.execute("""
        SELECT COUNT(*) as count 
        FROM information_schema.tables 
        WHERE table_schema = %s AND table_name = 'notifications'
    """, (db_name,))
    
    result = cursor.fetchone()
    
    if result['count'] > 0:
        print(f"   ℹ️  notifications table already exists!")
        print(f"\n   Do you want to drop and recreate it? (yes/no): ", end='')
        answer = input().strip().lower()
        
        if answer == 'yes':
            cursor.execute("DROP TABLE notifications")
            print("   🗑️  Old table dropped")
        else:
            print("\n   ✅ Keeping existing table. No changes made.\n")
            cursor.close()
            conn.close()
            sys.exit(0)
    
    # Create notifications table
    print("\n🔧 Creating notifications table...")
    
    cur.execute("""
        CREATE TABLE notifications (
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
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    
    conn.commit()
    
    print("   ✅ notifications table created successfully!")
    
    # Insert sample notification
    print("\n🔔 Creating sample notification...")
    cursor.execute("SELECT id FROM members LIMIT 1")
    member = cursor.fetchone()
    
    if member:
        cursor.execute("""
            INSERT INTO notifications (user_id, title, message, type, link)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            member['id'],
            "Welcome to Notifications!",
            "Your notification system is now active and working perfectly.",
            "success",
            "/notifications/"
        ))
        conn.commit()
        print(f"   ✅ Sample notification created for user ID: {member['id']}")
    
    # Show table info
    cursor.execute("DESCRIBE notifications")
    columns = cursor.fetchall()
    
    print("\n📊 Table Structure:")
    print("-" * 60)
    for col in columns:
        print(f"   {col['Field']:20} {col['Type']:30} {col['Null']}")
    
    cursor.close()
    conn.close()
    
    print("\n" + "="*60)
    print("✨ SUCCESS! Notifications table is ready to use!")
    print("="*60)
    print("\n💡 Now refresh your browser at: http://127.0.0.1:8000/notifications/\n")
    
except pymysql.Error as e:
    print(f"\n❌ Database Error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
