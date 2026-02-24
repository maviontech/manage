#!/usr/bin/env python3
"""
Update Developer role permissions to be more restrictive
Developer should only have:
- projects.view
- projects.create
- tasks.view (my tasks)
- tasks.view_unassigned
"""

import pymysql
import sys
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
import django
django.setup()

def update_developer_permissions():
    """Update Developer role with restricted permissions"""
    
    # Connect to master database first to get tenant info
    master_conn = pymysql.connect(
        host='localhost',
        user='root',
        password='root',
        database='master_db',
        cursorclass=pymysql.cursors.DictCursor
    )
    
    master_cur = master_conn.cursor()
    
    # Get all tenants
    master_cur.execute("SELECT id, client_name, db_name FROM clients_master ORDER BY id")
    tenants = master_cur.fetchall()
    
    master_cur.close()
    master_conn.close()
    
    if not tenants:
        print("❌ No tenants found in master database!")
        return
    
    print(f"\n=== Updating Developer Role Permissions ===")
    print(f"Found {len(tenants)} tenant(s)\n")
    
    # Define Developer permissions (RESTRICTED)
    developer_permissions = [
        'dashboard.view',
        'projects.view',
        'projects.create',
        'tasks.view',  # My tasks only
        'tasks.view_unassigned',
        'notifications.view',
    ]
    
    # Process each tenant
    for tenant in tenants:
        print(f"{'=' * 70}")
        print(f"Processing: {tenant['client_name']} ({tenant['db_name']})")
        print(f"{'=' * 70}")
        
        # Connect to tenant database
        conn = pymysql.connect(
            host='localhost',
            user='root',
            password='root',
            database=tenant['db_name'],
            cursorclass=pymysql.cursors.DictCursor
        )
        
        cur = conn.cursor()
        
        # Get Developer role ID
        cur.execute("SELECT id FROM roles WHERE name = 'Developer'")
        role = cur.fetchone()
        
        if not role:
            print(f"⚠️  Developer role not found in {tenant['db_name']}, skipping...")
            cur.close()
            conn.close()
            continue
        
        role_id = role['id']
        
        # Clear existing permissions for Developer role
        cur.execute("DELETE FROM role_permissions WHERE role_id = %s", (role_id,))
        print(f"✓ Cleared existing Developer permissions")
        
        # Add new restricted permissions
        print(f"\nAdding restricted permissions:")
        for perm_code in developer_permissions:
            cur.execute("SELECT id FROM permissions WHERE code = %s", (perm_code,))
            perm = cur.fetchone()
            if perm:
                cur.execute(
                    "INSERT INTO role_permissions (role_id, permission_id) VALUES (%s, %s)",
                    (role_id, perm['id'])
                )
                print(f"  ✓ {perm_code}")
            else:
                print(f"  ⚠️  Permission not found: {perm_code}")
        
        conn.commit()
        
        print(f"\n✅ Developer role updated in {tenant['client_name']}")
        print()
        
        cur.close()
        conn.close()
    
    print(f"{'=' * 70}")
    print("✅ ALL TENANTS UPDATED SUCCESSFULLY!")
    print(f"{'=' * 70}")
    print("\nDeveloper Role Now Has:")
    for perm in developer_permissions:
        print(f"  • {perm}")
    print("\nDeveloper Role DOES NOT Have:")
    print("  • tasks.create (cannot create tasks)")
    print("  • tasks.edit (cannot edit tasks)")
    print("  • tasks.view_board (cannot see task board)")
    print("  • tasks.view_analytics (cannot see analytics)")
    print("  • projects.edit (cannot edit projects)")
    print("  • Any other advanced permissions")

if __name__ == '__main__':
    try:
        update_developer_permissions()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
