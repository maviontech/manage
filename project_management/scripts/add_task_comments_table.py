#!/usr/bin/env python
"""
Migration script to add task_comments table to all tenant databases.
"""
import os
import sys
import pymysql

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

MASTER_DB = os.environ.get('MASTER_DB_NAME', 'master_db')
ADMIN_HOST = os.environ.get('MYSQL_ADMIN_HOST', '127.0.0.1')
ADMIN_PORT = int(os.environ.get('MYSQL_ADMIN_PORT', 3306))
ADMIN_USER = os.environ.get('MYSQL_ADMIN_USER', 'root')
ADMIN_PWD = os.environ.get('MYSQL_ADMIN_PWD', 'root')


def add_task_comments_table():
    """Add task_comments table to all tenant databases"""
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
        master_cur = master_conn.cursor()
        
        # Get all tenant databases
        master_cur.execute("SELECT db_name FROM tenants")
        tenants = master_cur.fetchall()
        
        master_cur.close()
        master_conn.close()
        
        if not tenants:
            print("No tenants found.")
            return
        
        print(f"Found {len(tenants)} tenant(s). Adding task_comments table...")
        
        # SQL to create task_comments table
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS task_comments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            task_id INT NOT NULL,
            comment_text TEXT NOT NULL,
            commenter_id INT NOT NULL,
            commenter_name VARCHAR(255),
            is_internal BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (commenter_id) REFERENCES members(id) ON DELETE CASCADE,
            INDEX idx_task (task_id),
            INDEX idx_commenter (commenter_id),
            INDEX idx_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        
        # Process each tenant
        success_count = 0
        error_count = 0
        
        for tenant in tenants:
            db_name = tenant['db_name']
            try:
                # Connect to tenant database
                tenant_conn = pymysql.connect(
                    host=ADMIN_HOST,
                    port=ADMIN_PORT,
                    user=ADMIN_USER,
                    password=ADMIN_PWD,
                    database=db_name,
                    cursorclass=pymysql.cursors.DictCursor
                )
                tenant_cur = tenant_conn.cursor()
                
                # Create task_comments table
                tenant_cur.execute(create_table_sql)
                tenant_conn.commit()
                
                tenant_cur.close()
                tenant_conn.close()
                
                print(f"✓ Added task_comments table to {db_name}")
                success_count += 1
                
            except Exception as e:
                print(f"✗ Error adding table to {db_name}: {str(e)}")
                error_count += 1
        
        print("\n" + "="*50)
        print(f"Migration completed!")
        print(f"Successful: {success_count}")
        print(f"Failed: {error_count}")
        print("="*50)
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    print("="*50)
    print("Adding task_comments table to tenant databases")
    print("="*50)
    add_task_comments_table()
