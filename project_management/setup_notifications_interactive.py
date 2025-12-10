"""
Interactive Notifications Table Setup
Run this script and follow the prompts
"""

import pymysql

print("\n" + "="*70)
print(" "*20 + "NOTIFICATIONS TABLE SETUP")
print("="*70)

print("\n📋 MySQL Connection Details")
print("-" * 70)

# Get database credentials
db_host = input("MySQL Host [localhost]: ").strip() or "localhost"
db_user = input("MySQL User [root]: ").strip() or "root"
db_password = input("MySQL Password [press Enter if none]: ").strip()
db_name = input("Database Name: ").strip()

if not db_name:
    print("\n❌ Database name is required!")
    exit(1)

print(f"\n🔌 Connecting to {db_user}@{db_host}/{db_name}...")

try:
    # Connect to the database
    conn = pymysql.connect(
        host=db_host,
        user=db_user,
        password=db_password if db_password else None,
        database=db_name,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    
    print("✅ Connected successfully!")
    
    cursor = conn.cursor()
    
    # Check if table already exists
    print(f"\n🔍 Checking if notifications table exists...")
    cursor.execute("""
        SELECT COUNT(*) as count 
        FROM information_schema.tables 
        WHERE table_schema = %s AND table_name = 'notifications'
    """, (db_name,))
    
    result = cursor.fetchone()
    
    if result['count'] > 0:
        print(f"   ⚠️  notifications table already exists!")
        print(f"\n   Drop and recreate? (yes/no): ", end='')
        answer = input().strip().lower()
        
        if answer != 'yes':
            print("\n   ✅ Keeping existing table. Exiting.\n")
            cursor.close()
            conn.close()
            exit(0)
        
        cursor.execute("DROP TABLE notifications")
        conn.commit()
        print("   🗑️  Old table dropped")
    
    # Create notifications table
    print("\n🔧 Creating notifications table...")
    
    cursor.execute("""
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
    
    print("   ✅ Table created successfully!")
    
    # Insert sample notifications
    print("\n🔔 Creating sample notifications...")
    
    cursor.execute("SELECT id, CONCAT(first_name, ' ', last_name) as name FROM members LIMIT 3")
    members = cursor.fetchall()
    
    if members:
        for member in members:
            cursor.execute("""
                INSERT INTO notifications (user_id, title, message, type, link)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                member['id'],
                "Welcome to Notifications!",
                f"Hi {member['name']}, your notification system is now active and ready to use.",
                "success",
                "/notifications/"
            ))
        conn.commit()
        print(f"   ✅ Created {len(members)} sample notification(s)")
    else:
        print("   ⚠️  No members found - skipping sample notifications")
    
    # Show table info
    print("\n📊 Table Structure:")
    print("-" * 70)
    cursor.execute("DESCRIBE notifications")
    columns = cursor.fetchall()
    
    print(f"{'Field':<20} {'Type':<35} {'Null':<8} {'Key'}")
    print("-" * 70)
    for col in columns:
        print(f"{col['Field']:<20} {col['Type']:<35} {col['Null']:<8} {col['Key']}")
    
    # Count notifications
    cursor.execute("SELECT COUNT(*) as count FROM notifications")
    count_result = cursor.fetchone()
    
    print(f"\n📈 Total Notifications: {count_result['count']}")
    
    cursor.close()
    conn.close()
    
    print("\n" + "="*70)
    print("✨ SUCCESS! Your notifications system is ready!")
    print("="*70)
    print("\n💡 Actions:")
    print(f"   1. Restart your Django server if it's running")
    print(f"   2. Visit: http://127.0.0.1:8000/notifications/")
    print(f"   3. Check the bell icon in the header for notifications")
    print()
    
except pymysql.Error as e:
    print(f"\n❌ Database Error:")
    print(f"   {e}")
    print("\n💡 Common fixes:")
    print("   - Check your MySQL username and password")
    print("   - Make sure the database exists")
    print("   - Verify MySQL server is running")
    print()
    exit(1)
except Exception as e:
    print(f"\n❌ Unexpected Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
