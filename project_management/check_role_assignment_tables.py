#!/usr/bin/env python3
"""
Check which role assignment tables exist and have data
"""

import pymysql
import sys
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
import django
django.setup()

def check_tables():
    """Check role assignment tables"""
    
    conn = pymysql.connect(
        host='localhost',
        user='root',
        password='root',
        database='Maviontech_db_demo',
        cursorclass=pymysql.cursors.DictCursor
    )
    
    cur = conn.cursor()
    
    print("\n" + "=" * 70)
    print("CHECKING ROLE ASSIGNMENT TABLES")
    print("=" * 70)
    
    # Check if tenant_role_assignments table exists
    cur.execute("SHOW TABLES LIKE 'tenant_role_assignments'")
    tenant_table_exists = cur.fetchone()
    
    print(f"\n1. tenant_role_assignments table:")
    if tenant_table_exists:
        print(f"   ✓ EXISTS")
        
        # Check data
        cur.execute("SELECT COUNT(*) as count FROM tenant_role_assignments")
        count = cur.fetchone()['count']
        print(f"   Records: {count}")
        
        if count > 0:
            cur.execute("""
                SELECT tra.*, r.name as role_name, u.email
                FROM tenant_role_assignments tra
                JOIN roles r ON tra.role_id = r.id
                JOIN users u ON tra.member_id = u.id
            """)
            records = cur.fetchall()
            print(f"   Data:")
            for rec in records:
                print(f"     • {rec['email']} → {rec['role_name']}")
    else:
        print(f"   ❌ DOES NOT EXIST")
    
    # Check project_role_assignments table
    cur.execute("SHOW TABLES LIKE 'project_role_assignments'")
    project_table_exists = cur.fetchone()
    
    print(f"\n2. project_role_assignments table:")
    if project_table_exists:
        print(f"   ✓ EXISTS")
        
        # Check data
        cur.execute("SELECT COUNT(*) as count FROM project_role_assignments")
        count = cur.fetchone()['count']
        print(f"   Records: {count}")
        
        if count > 0:
            cur.execute("""
                SELECT pra.*, r.name as role_name, u.email, p.name as project_name
                FROM project_role_assignments pra
                JOIN roles r ON pra.role_id = r.id
                JOIN users u ON pra.member_id = u.id
                JOIN projects p ON pra.project_id = p.id
            """)
            records = cur.fetchall()
            print(f"   Data:")
            for rec in records:
                print(f"     • {rec['email']} → {rec['role_name']} in project '{rec['project_name']}'")
    else:
        print(f"   ❌ DOES NOT EXIST")
    
    # Check users table
    print(f"\n3. All users:")
    cur.execute("SELECT id, email, full_name FROM users")
    users = cur.fetchall()
    for user in users:
        print(f"   • ID: {user['id']}, Email: {user['email']}, Name: {user['full_name']}")
    
    print(f"\n{'=' * 70}")
    print("ANALYSIS:")
    print(f"{'=' * 70}")
    
    if not tenant_table_exists:
        print("\n❌ CRITICAL ISSUE: tenant_role_assignments table does NOT exist!")
        print("   The rbac.py code expects this table but it's missing.")
        print("   This is why permissions are not working!")
        print("\n   SOLUTION: Either:")
        print("   1. Create the tenant_role_assignments table, OR")
        print("   2. Modify rbac.py to only use project_role_assignments")
    elif tenant_table_exists and count == 0:
        print("\n⚠️  WARNING: tenant_role_assignments table exists but is EMPTY!")
        print("   Users only have project-specific role assignments.")
        print("   For permissions to work, users need EITHER:")
        print("   1. Tenant-wide role assignment, OR")
        print("   2. Project-specific role assignment")
        print("\n   Current situation: Users only have project assignments")
        print("   This means permissions only work in project context!")
    
    cur.close()
    conn.close()

if __name__ == '__main__':
    try:
        check_tables()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
