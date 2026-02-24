#!/usr/bin/env python3
"""
Verify bulk import permission exists and is assigned correctly
"""

import pymysql
import sys
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
import django
django.setup()

def verify_bulk_import():
    """Verify bulk import permission"""
    
    conn = pymysql.connect(
        host='localhost',
        user='root',
        password='root',
        database='Maviontech_db_demo',
        cursorclass=pymysql.cursors.DictCursor
    )
    
    cur = conn.cursor()
    
    print("\n" + "=" * 70)
    print("VERIFYING BULK IMPORT PERMISSION")
    print("=" * 70)
    
    # Check if permission exists
    cur.execute("SELECT id, code, description FROM permissions WHERE code = 'tasks.bulk_import'")
    perm = cur.fetchone()
    
    if perm:
        print(f"\n✅ Permission EXISTS:")
        print(f"   ID: {perm['id']}")
        print(f"   Code: {perm['code']}")
        print(f"   Description: {perm['description']}")
        
        # Check which roles have this permission
        cur.execute("""
            SELECT r.id, r.name
            FROM role_permissions rp
            JOIN roles r ON rp.role_id = r.id
            WHERE rp.permission_id = %s
            ORDER BY r.name
        """, (perm['id'],))
        
        roles = cur.fetchall()
        
        if roles:
            print(f"\n✅ Assigned to {len(roles)} role(s):")
            for role in roles:
                print(f"   • {role['name']} (ID: {role['id']})")
        else:
            print(f"\n⚠️  NOT assigned to any role!")
            print(f"   Admin needs to assign this permission via Roles UI")
    else:
        print(f"\n❌ Permission DOES NOT EXIST!")
        print(f"   Need to run: .venv\\Scripts\\python.exe add_comprehensive_permissions.py")
    
    # Check the view decorator
    print(f"\n{'=' * 70}")
    print("VIEW CONFIGURATION:")
    print(f"{'=' * 70}")
    print(f"\nView: bulk_import_csv_view")
    print(f"URL: /tasks/bulk-import/")
    print(f"Required Permission: tasks.bulk_import")
    print(f"Decorator: @require_permission('tasks.bulk_import')")
    
    print(f"\n{'=' * 70}")
    print("HOW TO GIVE ACCESS:")
    print(f"{'=' * 70}")
    print(f"\n1. Login as Admin")
    print(f"2. Go to Settings → Roles & Permissions")
    print(f"3. Click on the role (e.g., Developer)")
    print(f"4. Check ☑ 'tasks.bulk_import' checkbox")
    print(f"5. Click 'Save role' button")
    print(f"\nThen the user with that role can access /tasks/bulk-import/")
    
    cur.close()
    conn.close()

if __name__ == '__main__':
    try:
        verify_bulk_import()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
