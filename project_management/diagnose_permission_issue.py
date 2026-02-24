#!/usr/bin/env python3
"""
Diagnose permission issues - Check if admin's permission assignments are working
"""

import pymysql
import sys
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
import django
django.setup()

def diagnose_permissions():
    """Diagnose permission configuration and identify issues"""
    
    # Connect to tenant database
    conn = pymysql.connect(
        host='localhost',
        user='root',
        password='root',
        database='Maviontech_db_demo',
        cursorclass=pymysql.cursors.DictCursor
    )
    
    cur = conn.cursor()
    
    print("\n" + "=" * 70)
    print("PERMISSION SYSTEM DIAGNOSTIC")
    print("=" * 70)
    
    # Check all roles and their permissions
    cur.execute("SELECT id, name, description FROM roles ORDER BY name")
    roles = cur.fetchall()
    
    print(f"\n{'=' * 70}")
    print(f"ALL ROLES IN SYSTEM:")
    print(f"{'=' * 70}")
    
    for role in roles:
        print(f"\n{role['name']} (ID: {role['id']})")
        print(f"  Description: {role['description']}")
        
        # Get permissions for this role
        cur.execute("""
            SELECT p.code, p.description
            FROM role_permissions rp
            JOIN permissions p ON rp.permission_id = p.id
            WHERE rp.role_id = %s
            ORDER BY p.code
        """, (role['id'],))
        
        perms = cur.fetchall()
        print(f"  Permissions ({len(perms)}):")
        
        if perms:
            for perm in perms:
                print(f"    • {perm['code']:<30} - {perm['description']}")
        else:
            print(f"    (No permissions assigned)")
    
    # Check for users and their role assignments
    print(f"\n{'=' * 70}")
    print(f"USER ROLE ASSIGNMENTS:")
    print(f"{'=' * 70}")
    
    cur.execute("""
        SELECT DISTINCT
            u.id,
            u.email,
            u.full_name,
            pra.project_id,
            p.name as project_name,
            r.name as role_name,
            r.id as role_id
        FROM users u
        LEFT JOIN project_role_assignments pra ON u.id = pra.member_id
        LEFT JOIN projects p ON pra.project_id = p.id
        LEFT JOIN roles r ON pra.role_id = r.id
        ORDER BY u.email, p.name
    """)
    
    assignments = cur.fetchall()
    
    if assignments:
        current_user = None
        for assign in assignments:
            if assign['email'] != current_user:
                current_user = assign['email']
                print(f"\n{assign['email']} ({assign['full_name']})")
            
            if assign['project_name']:
                print(f"  Project: {assign['project_name']}")
                print(f"    Role: {assign['role_name']} (ID: {assign['role_id']})")
            else:
                print(f"  (No project assignments)")
    else:
        print("  (No user role assignments found)")
    
    # Check for common permission issues
    print(f"\n{'=' * 70}")
    print(f"COMMON ISSUES CHECK:")
    print(f"{'=' * 70}")
    
    issues_found = []
    
    # Issue 1: Roles with no permissions
    cur.execute("""
        SELECT r.id, r.name
        FROM roles r
        LEFT JOIN role_permissions rp ON r.id = rp.role_id
        WHERE rp.role_id IS NULL
    """)
    empty_roles = cur.fetchall()
    
    if empty_roles:
        issues_found.append("Roles with no permissions")
        print(f"\n⚠️  ISSUE: Roles with NO permissions assigned:")
        for role in empty_roles:
            print(f"  • {role['name']} (ID: {role['id']})")
    else:
        print(f"\n✅ All roles have at least one permission")
    
    # Issue 2: Users with no role assignments
    cur.execute("""
        SELECT u.id, u.email
        FROM users u
        LEFT JOIN project_role_assignments pra ON u.id = pra.member_id
        WHERE pra.member_id IS NULL
    """)
    unassigned_users = cur.fetchall()
    
    if unassigned_users:
        issues_found.append("Users with no role assignments")
        print(f"\n⚠️  ISSUE: Users with NO role assignments:")
        for user in unassigned_users:
            print(f"  • {user['email']} (ID: {user['id']})")
    else:
        print(f"\n✅ All users have role assignments")
    
    # Issue 3: Check if permission codes match what views expect
    expected_permissions = [
        'tasks.view',
        'tasks.view_unassigned',
        'tasks.view_board',
        'tasks.view_analytics',
        'roles.view',
        'roles.manage',
    ]
    
    print(f"\n{'=' * 70}")
    print(f"CHECKING CRITICAL PERMISSIONS:")
    print(f"{'=' * 70}")
    
    for perm_code in expected_permissions:
        cur.execute("SELECT id, code, description FROM permissions WHERE code = %s", (perm_code,))
        perm = cur.fetchone()
        
        if perm:
            # Check which roles have this permission
            cur.execute("""
                SELECT r.name
                FROM role_permissions rp
                JOIN roles r ON rp.role_id = r.id
                WHERE rp.permission_id = %s
                ORDER BY r.name
            """, (perm['id'],))
            
            roles_with_perm = cur.fetchall()
            role_names = [r['name'] for r in roles_with_perm]
            
            if role_names:
                print(f"\n✅ {perm_code}")
                print(f"   Assigned to: {', '.join(role_names)}")
            else:
                print(f"\n⚠️  {perm_code}")
                print(f"   NOT assigned to any role!")
                issues_found.append(f"Permission {perm_code} not assigned")
        else:
            print(f"\n❌ {perm_code}")
            print(f"   Permission does NOT exist in database!")
            issues_found.append(f"Permission {perm_code} missing")
    
    # Summary
    print(f"\n{'=' * 70}")
    print(f"DIAGNOSTIC SUMMARY:")
    print(f"{'=' * 70}")
    
    if issues_found:
        print(f"\n⚠️  {len(issues_found)} ISSUE(S) FOUND:")
        for i, issue in enumerate(issues_found, 1):
            print(f"  {i}. {issue}")
        print(f"\nRECOMMENDATIONS:")
        print(f"  1. Use the Roles UI to assign permissions to roles")
        print(f"  2. Ensure users are assigned to roles in projects")
        print(f"  3. Run add_comprehensive_permissions.py if permissions are missing")
    else:
        print(f"\n✅ NO ISSUES FOUND!")
        print(f"\nThe permission system appears to be configured correctly.")
        print(f"If users still can't access features, check:")
        print(f"  1. User is logged in with correct tenant")
        print(f"  2. User has role assignment in the specific project")
        print(f"  3. Session data is correct (member_id, tenant_config)")
        print(f"  4. Browser cache is cleared")
    
    cur.close()
    conn.close()

if __name__ == '__main__':
    try:
        diagnose_permissions()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
