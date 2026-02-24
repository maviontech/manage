#!/usr/bin/env python3
"""
Test the actual permission checking flow for a developer user
"""

import pymysql
import sys
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
import django
django.setup()

from django.test import RequestFactory
from core.rbac import has_permission, get_user_roles, get_role_permissions
from core.db_helpers import get_tenant_conn

def test_permission_flow():
    """Test permission checking for developer user"""
    
    # Connect to database
    conn = pymysql.connect(
        host='localhost',
        user='root',
        password='root',
        database='Maviontech_db_demo',
        cursorclass=pymysql.cursors.DictCursor
    )
    
    cur = conn.cursor()
    
    print("\n" + "=" * 70)
    print("TESTING PERMISSION CHECK FLOW FOR DEVELOPER USER")
    print("=" * 70)
    
    # Get developer user
    cur.execute("SELECT id, email FROM users WHERE email = 'vishal12@maviontech.com'")
    user = cur.fetchone()
    
    if not user:
        print("❌ Developer user not found!")
        return
    
    member_id = user['id']
    print(f"\n✓ Testing with user: {user['email']} (ID: {member_id})")
    
    # Step 1: Get user's roles
    print(f"\n{'=' * 70}")
    print("STEP 1: Getting user's roles")
    print(f"{'=' * 70}")
    
    role_ids = get_user_roles(conn, member_id, project_id=None)
    print(f"Role IDs found: {role_ids}")
    
    if role_ids:
        # Get role names
        placeholders = ','.join(['%s'] * len(role_ids))
        cur.execute(f"SELECT id, name FROM roles WHERE id IN ({placeholders})", tuple(role_ids))
        roles = cur.fetchall()
        print(f"Roles:")
        for role in roles:
            print(f"  • {role['name']} (ID: {role['id']})")
    else:
        print("❌ NO ROLES FOUND!")
    
    # Step 2: Get permissions for those roles
    print(f"\n{'=' * 70}")
    print("STEP 2: Getting permissions for roles")
    print(f"{'=' * 70}")
    
    permissions = get_role_permissions(conn, role_ids)
    print(f"Permissions found: {len(permissions)}")
    if permissions:
        for perm in sorted(permissions):
            print(f"  • {perm}")
    else:
        print("❌ NO PERMISSIONS FOUND!")
    
    # Step 3: Test specific permission checks
    print(f"\n{'=' * 70}")
    print("STEP 3: Testing specific permissions")
    print(f"{'=' * 70}")
    
    test_permissions = [
        'tasks.edit',
        'tasks.view',
        'tasks.view_analytics',
        'employees.view',
        'projects.create',
        'tasks.view_board',
    ]
    
    # Create a mock request
    factory = RequestFactory()
    request = factory.get('/')
    request.session = {'member_id': member_id, 'tenant_config': {'database': 'Maviontech_db_demo'}}
    
    for perm_code in test_permissions:
        has_perm = has_permission(request, perm_code)
        in_set = perm_code in permissions
        
        status = "✅" if has_perm else "❌"
        match = "✓" if has_perm == in_set else "✗ MISMATCH"
        
        print(f"{status} {perm_code:<30} (in set: {in_set}) {match}")
    
    # Step 4: Check database directly
    print(f"\n{'=' * 70}")
    print("STEP 4: Direct database check")
    print(f"{'=' * 70}")
    
    # Check project role assignments
    cur.execute("""
        SELECT pra.*, r.name as role_name, p.name as project_name
        FROM project_role_assignments pra
        JOIN roles r ON pra.role_id = r.id
        JOIN projects p ON pra.project_id = p.id
        WHERE pra.member_id = %s
    """, (member_id,))
    
    assignments = cur.fetchall()
    print(f"\nProject Role Assignments:")
    for assign in assignments:
        print(f"  • Project: {assign['project_name']}")
        print(f"    Role: {assign['role_name']} (ID: {assign['role_id']})")
        
        # Get permissions for this role
        cur.execute("""
            SELECT p.code
            FROM role_permissions rp
            JOIN permissions p ON rp.permission_id = p.id
            WHERE rp.role_id = %s
            ORDER BY p.code
        """, (assign['role_id'],))
        
        role_perms = cur.fetchall()
        print(f"    Permissions ({len(role_perms)}):")
        for perm in role_perms:
            print(f"      • {perm['code']}")
    
    # Check tenant role assignments
    cur.execute("""
        SELECT tra.*, r.name as role_name
        FROM tenant_role_assignments tra
        JOIN roles r ON tra.role_id = r.id
        WHERE tra.member_id = %s
    """, (member_id,))
    
    tenant_assignments = cur.fetchall()
    print(f"\nTenant Role Assignments:")
    if tenant_assignments:
        for assign in tenant_assignments:
            print(f"  • Role: {assign['role_name']} (ID: {assign['role_id']})")
    else:
        print(f"  (None - user only has project-specific roles)")
    
    print(f"\n{'=' * 70}")
    print("CONCLUSION:")
    print(f"{'=' * 70}")
    
    if not role_ids:
        print("\n❌ PROBLEM: User has NO roles found by get_user_roles()")
        print("   This is why permissions are not working!")
    elif not permissions:
        print("\n❌ PROBLEM: Roles found but NO permissions!")
        print("   Check role_permissions table")
    else:
        print(f"\n✅ User has {len(role_ids)} role(s) with {len(permissions)} permission(s)")
        print("   Permission system should be working")
    
    cur.close()
    conn.close()

if __name__ == '__main__':
    try:
        test_permission_flow()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
