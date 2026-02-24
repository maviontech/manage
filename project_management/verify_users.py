#!/usr/bin/env python
"""
Complete User and RBAC System Verification
Checks all users, their roles, and permissions
"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
django.setup()

import pymysql
from datetime import datetime

# Connect to database
conn = pymysql.connect(
    host='127.0.0.1',
    port=3306,
    user='root',
    password='root',
    database='simployfyd_db',
    cursorclass=pymysql.cursors.DictCursor
)

cur = conn.cursor()

print("\n" + "="*80)
print("COMPLETE SYSTEM VERIFICATION")
print("="*80)
print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*80)

# 1. Check all users
print("\n1. ALL USERS IN SYSTEM")
print("-" * 80)
cur.execute("SELECT id, email, full_name, role, is_active, created_at FROM users ORDER BY id")
users = cur.fetchall()

print(f"\nTotal Users: {len(users)}\n")
for user in users:
    status = "✓ Active" if user['is_active'] else "✗ Inactive"
    legacy_role = user['role'] or "NULL (uses RBAC)"
    print(f"ID: {user['id']}")
    print(f"  Email: {user['email']}")
    print(f"  Name: {user['full_name']}")
    print(f"  Legacy Role Column: {legacy_role}")
    print(f"  Status: {status}")
    print(f"  Created: {user['created_at']}")
    print()

# 2. Check role assignments
print("\n2. ROLE ASSIGNMENTS (ACTIVE RBAC)")
print("-" * 80)
cur.execute("""
    SELECT 
        u.id as user_id,
        u.email,
        u.full_name,
        r.name as role_name,
        p.name as project_name,
        pra.assigned_at
    FROM project_role_assignments pra
    JOIN users u ON pra.member_id = u.id
    JOIN roles r ON pra.role_id = r.id
    LEFT JOIN projects p ON pra.project_id = p.id
    ORDER BY u.id, pra.assigned_at DESC
""")
assignments = cur.fetchall()

if assignments:
    print(f"\nTotal Role Assignments: {len(assignments)}\n")
    for assign in assignments:
        print(f"✓ {assign['full_name']} ({assign['email']})")
        print(f"  Role: {assign['role_name']}")
        print(f"  Project: {assign['project_name']}")
        print(f"  Assigned: {assign['assigned_at']}")
        print()
else:
    print("\n⚠️ No role assignments found!")
    print("Users need to be assigned roles via Settings → Access Control\n")

# 3. Check each user's effective permissions
print("\n3. USER PERMISSIONS BREAKDOWN")
print("-" * 80)

for user in users:
    print(f"\n{user['full_name']} ({user['email']})")
    print("-" * 40)
    
    # Get roles
    cur.execute("""
        SELECT DISTINCT r.name, p.name as project_name
        FROM project_role_assignments pra
        JOIN roles r ON pra.role_id = r.id
        LEFT JOIN projects p ON pra.project_id = p.id
        WHERE pra.member_id = %s
    """, (user['id'],))
    user_roles = cur.fetchall()
    
    if user_roles:
        print("Roles:")
        for role in user_roles:
            print(f"  • {role['name']} (Project: {role['project_name']})")
        
        # Get permissions
        cur.execute("""
            SELECT DISTINCT p.code
            FROM project_role_assignments pra
            JOIN role_permissions rp ON pra.role_id = rp.role_id
            JOIN permissions p ON rp.permission_id = p.id
            WHERE pra.member_id = %s
            ORDER BY p.code
        """, (user['id'],))
        perms = cur.fetchall()
        
        if perms:
            print(f"\nPermissions ({len(perms)} total):")
            for perm in perms:
                print(f"  ✓ {perm['code']}")
        else:
            print("\n⚠️ Role has no permissions assigned!")
    else:
        print("⚠️ No roles assigned")
        print("Action needed: Assign role via Settings → Access Control")

# 4. Check all available roles
print("\n\n4. AVAILABLE ROLES")
print("-" * 80)
cur.execute("SELECT * FROM roles ORDER BY id")
roles = cur.fetchall()

for role in roles:
    print(f"\n{role['name']} (ID: {role['id']})")
    
    # Get permissions for this role
    cur.execute("""
        SELECT p.code, p.description
        FROM role_permissions rp
        JOIN permissions p ON rp.permission_id = p.id
        WHERE rp.role_id = %s
        ORDER BY p.code
    """, (role['id'],))
    role_perms = cur.fetchall()
    
    if role_perms:
        print(f"  Permissions: {len(role_perms)}")
        for perm in role_perms:
            print(f"    • {perm['code']}")
    else:
        print("  ⚠️ No permissions assigned to this role!")

# 5. Check projects
print("\n\n5. PROJECTS")
print("-" * 80)
cur.execute("SELECT id, name, status, created_at FROM projects ORDER BY id")
projects = cur.fetchall()

if projects:
    print(f"\nTotal Projects: {len(projects)}\n")
    for proj in projects:
        print(f"• {proj['name']} (ID: {proj['id']})")
        print(f"  Status: {proj['status']}")
        print(f"  Created: {proj['created_at']}")
        
        # Count role assignments for this project
        cur.execute("""
            SELECT COUNT(*) as count
            FROM project_role_assignments
            WHERE project_id = %s
        """, (proj['id'],))
        count = cur.fetchone()['count']
        print(f"  Team Members: {count}")
        print()
else:
    print("\n⚠️ No projects found!")

# 6. System health check
print("\n6. SYSTEM HEALTH CHECK")
print("-" * 80)

checks = []

# Check 1: Users with roles
cur.execute("SELECT COUNT(*) as count FROM project_role_assignments")
role_count = cur.fetchone()['count']
checks.append(("Users with roles assigned", role_count > 0, f"{role_count} assignments"))

# Check 2: Roles with permissions
cur.execute("SELECT COUNT(DISTINCT role_id) as count FROM role_permissions")
roles_with_perms = cur.fetchone()['count']
checks.append(("Roles with permissions", roles_with_perms > 0, f"{roles_with_perms} roles configured"))

# Check 3: Active users
cur.execute("SELECT COUNT(*) as count FROM users WHERE is_active = 1")
active_users = cur.fetchone()['count']
checks.append(("Active users", active_users > 0, f"{active_users} active"))

# Check 4: Projects exist
cur.execute("SELECT COUNT(*) as count FROM projects")
project_count = cur.fetchone()['count']
checks.append(("Projects created", project_count > 0, f"{project_count} projects"))

print()
for check_name, passed, detail in checks:
    status = "✓" if passed else "✗"
    print(f"{status} {check_name}: {detail}")

# 7. Recommendations
print("\n\n7. RECOMMENDATIONS")
print("-" * 80)

recommendations = []

# Check for users without roles
cur.execute("""
    SELECT u.email, u.full_name
    FROM users u
    LEFT JOIN project_role_assignments pra ON u.id = pra.member_id
    WHERE pra.id IS NULL AND u.is_active = 1
""")
users_without_roles = cur.fetchall()

if users_without_roles:
    recommendations.append(("Assign roles to users", [
        f"• {u['full_name']} ({u['email']}) has no role assigned"
        for u in users_without_roles
    ]))

# Check for roles without permissions
cur.execute("""
    SELECT r.name
    FROM roles r
    LEFT JOIN role_permissions rp ON r.id = rp.role_id
    WHERE rp.id IS NULL
""")
roles_without_perms = cur.fetchall()

if roles_without_perms:
    recommendations.append(("Configure role permissions", [
        f"• {r['name']} role has no permissions"
        for r in roles_without_perms
    ]))

if recommendations:
    print()
    for title, items in recommendations:
        print(f"⚠️ {title}:")
        for item in items:
            print(f"  {item}")
        print()
else:
    print("\n✓ No recommendations - system is fully configured!")

# 8. Summary
print("\n" + "="*80)
print("SUMMARY")
print("="*80)

print(f"""
Total Users: {len(users)}
  - Active: {active_users}
  - With Roles: {role_count}
  - Without Roles: {len(users_without_roles)}

Total Roles: {len(roles)}
  - With Permissions: {roles_with_perms}

Total Projects: {project_count}

System Status: {"✓ OPERATIONAL" if all(c[1] for c in checks) else "⚠️ NEEDS ATTENTION"}
""")

print("="*80)
print("\nHow to assign roles to users:")
print("  1. Login as admin")
print("  2. Go to: Settings → Access Control")
print("  3. Select project, member, and role")
print("  4. Click 'Assign' button")
print("\nHow to manage permissions:")
print("  1. Login as admin")
print("  2. Go to: Settings → Roles & Permissions")
print("  3. Click on a role")
print("  4. Check/uncheck permissions")
print("  5. Click 'Save role'")
print("="*80 + "\n")

cur.close()
conn.close()
