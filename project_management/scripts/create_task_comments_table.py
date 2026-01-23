#!/usr/bin/env python
"""
Add task_comments table to current database
"""
import os
import sys
import django

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
django.setup()

import pymysql
from django.conf import settings

def add_task_comments_table():
    """Add task_comments table to hacker_db_main database"""
    try:
        # Connect using Django database settings or fallback to defaults
        conn = pymysql.connect(
            host=os.environ.get('MYSQL_ADMIN_HOST', '127.0.0.1'),
            port=int(os.environ.get('MYSQL_ADMIN_PORT', 3306)),
            user=os.environ.get('MYSQL_ADMIN_USER', 'root'),
            password=os.environ.get('MYSQL_ADMIN_PWD', 'root'),
            database='hacker_db_main',  # Your database name from error
            cursorclass=pymysql.cursors.DictCursor
        )
        cur = conn.cursor()
        
        print("Creating task_comments table...")
        
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
        
        cur.execute(create_table_sql)
        conn.commit()
        
        print("✓ task_comments table created successfully!")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    print("="*50)
    print("Adding task_comments table")
    print("="*50)
    add_task_comments_table()
