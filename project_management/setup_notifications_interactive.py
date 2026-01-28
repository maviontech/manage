"""
Interactive Notifications Table Setup
Run this script and follow the prompts
"""

import pymysql
import logging

# Use project logger
logger = logging.getLogger('project_management')

logger.info("\n" + "="*70)
logger.info(" "*20 + "NOTIFICATIONS TABLE SETUP")
logger.info("="*70)

logger.info("\n📋 MySQL Connection Details")
logger.info("-" * 70)

# Get database credentials
db_host = input("MySQL Host [localhost]: ").strip() or "localhost"
db_user = input("MySQL User [root]: ").strip() or "root"
db_password = input("MySQL Password [press Enter if none]: ").strip()
db_name = input("Database Name: ").strip()

if not db_name:
    logger.error("\n❌ Database name is required!")
    exit(1)

logger.info(f"\n🔌 Connecting to {db_user}@{db_host}/{db_name}...")

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
    
    logger.info("✅ Connected successfully!")
    
    cursor = conn.cursor()
    
    # Check if table already exists
    logger.info(f"\n🔍 Checking if notifications table exists...")
    cursor.execute("""
        SELECT COUNT(*) as count 
        FROM information_schema.tables 
        WHERE table_schema = %s AND table_name = 'notifications'
    """, (db_name,))
    
    result = cursor.fetchone()
    
    if result['count'] > 0:
        logger.warning(f"   ⚠️  notifications table already exists!")
        logger.info(f"\n   Drop and recreate? (yes/no): ")
        answer = input().strip().lower()
        
        if answer != 'yes':
            logger.info("\n   ✅ Keeping existing table. Exiting.\n")
            cursor.close()
            conn.close()
            exit(0)
        
        cursor.execute("DROP TABLE notifications")
        conn.commit()
        logger.info("   🗑️  Old table dropped")
    
    # Create notifications table
    logger.info("\n🔧 Creating notifications table...")
    
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
    
    logger.info("   ✅ Table created successfully!")
    
    # Insert sample notifications
    logger.info("\n🔔 Creating sample notifications...")
    
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
        logger.info(f"   ✅ Created {len(members)} sample notification(s)")
    else:
        logger.warning("   ⚠️  No members found - skipping sample notifications")
    
    # Show table info
    logger.info("\n📊 Table Structure:")
    logger.info("-" * 70)
    cursor.execute("DESCRIBE notifications")
    columns = cursor.fetchall()
    
    logger.info(f"{'Field':<20} {'Type':<35} {'Null':<8} {'Key'}")
    logger.info("-" * 70)
    for col in columns:
        logger.info(f"{col['Field']:<20} {col['Type']:<35} {col['Null']:<8} {col['Key']}")
    
    # Count notifications
    cursor.execute("SELECT COUNT(*) as count FROM notifications")
    count_result = cursor.fetchone()
    
    logger.info(f"\n📈 Total Notifications: {count_result['count']}")
    
    cursor.close()
    conn.close()
    
    logger.info ("\n" + "="*70)
    logger.info("✨ SUCCESS! Your notifications system is ready!")
    logger.info("="*70)
    logger.info("\n💡 Actions:")
    logger.info(f"   1. Restart your Django server if it's running")
    logger.info(f"   2. Visit: http://127.0.0.1:8000/notifications/")
    logger.info(f"   3. Check the bell icon in the header for notifications")
    
except pymysql.Error as e:
    logger.error(f"\n❌ Database Error:")
    logger.error(f"   {e}")
    logger.error("\n💡 Common fixes:")
    logger.error("   - Check your MySQL username and password")
    logger.error("   - Make sure the database exists")
    logger.error("   - Verify MySQL server is running")
    logger.error("")
    exit(1)
except Exception as e:
    logger.error(f"\n❌ Unexpected Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
