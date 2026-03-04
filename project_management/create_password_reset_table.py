import pymysql
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
django.setup()

from django.conf import settings

# Connect to MySQL admin
conn = pymysql.connect(
    host=settings.MYSQL_ADMIN_HOST,
    port=settings.MYSQL_ADMIN_PORT,
    user=settings.MYSQL_ADMIN_USER,
    password=settings.MYSQL_ADMIN_PWD,
    cursorclass=pymysql.cursors.DictCursor
)

cur = conn.cursor()

# Check specific tenant databases
tenant_dbs = ['maviontech_db_demo', 'c2h_management', 'simployfyd_db']

print("Creating password_reset_tokens table in tenant databases...\n")

for db_name in tenant_dbs:
    # Check if database exists
    cur.execute("SHOW DATABASES LIKE %s", (db_name,))
    if not cur.fetchone():
        print(f"⚠️  Database '{db_name}' does not exist, skipping...")
        continue
    
    print(f"\n{db_name}:")
    cur.execute(f"USE {db_name}")
    
    # Check if table exists
    cur.execute("""
        SELECT COUNT(*) as count 
        FROM information_schema.tables 
        WHERE table_schema = %s 
        AND table_name = 'password_reset_tokens'
    """, (db_name,))
    
    result = cur.fetchone()
    
    if result['count'] == 0:
        print("  ❌ Table 'password_reset_tokens' does NOT exist")
        print("  Creating table...")
        
        try:
            # Create the table
            cur.execute("""
                CREATE TABLE password_reset_tokens (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    token VARCHAR(255) NOT NULL UNIQUE,
                    expires_at DATETIME NOT NULL,
                    used TINYINT(1) DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    INDEX idx_token (token),
                    INDEX idx_expires (expires_at)
                )
            """)
            conn.commit()
            print("  ✅ Table created successfully")
        except Exception as e:
            print(f"  ❌ Error creating table: {e}")
    else:
        print("  ✅ Table already exists")
        
        # Show table structure
        cur.execute("DESCRIBE password_reset_tokens")
        columns = cur.fetchall()
        print("  Columns:")
        for col in columns:
            print(f"    - {col['Field']}: {col['Type']}")

cur.close()
conn.close()

print("\n✅ Setup complete!")
