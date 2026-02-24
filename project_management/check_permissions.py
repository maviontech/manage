#!/usr/bin/env python
"""Check current role permissions in database"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
django.setup()

import pymysql

conn = pymysql.connect(
    host='127.0.0.1',
    port=3306,
    user='root',
    password='root',
    database='simployfyd_db',
    cursorclass=pymysql.cursors.DictCursor
)

cur = conn.cursor()

print("\n" + "="*60)
print("CURRENT ROLE PERMISSIONS IN DATABASE")
print("="*60)

# Get all role permissions
cur.execute("""
    SELECT 
        r.id as role_id,
        r.name as role_name,
        p.id as permission_id,
        p.code as permission_code,
        p.description as permission_desc
    FROM role_permissions rp
    JOIN roles r ON rp.role_id = r.id
    JOIN permissions p ON rp.permission_id = p.id
    ORDER BY r.name, p.code
""")

rows = cur.fetchall()

if rows:
    current_role = None
    for row in rows:
        if row['role_name'] != current_role:
            print(f"\n{row['role_name']}:")
            current_role = row['role_name']
        print(f"  ✓ {row['permission_code']}")
else:
    print("\n⚠️ NO PERMISSIONS ASSIGNED TO ANY ROLE!")
    print("\nThis means the role_permissions table is empty.")
    print("You need to assign permissions to roles via the UI.")

# Check if Developer role has the permissions you mentioned
print("\n" + "="*60)
print("CHECKING DEVELOPER ROLE SPECIFICALLY")
print("="*60)

cur.execute("""
    SELECT p.code
    FROM role_permissions rp
    JOIN roles r ON rp.role_id = r.id
    JOIN permissions p ON rp.permission_id = p.id
    WHERE r.name = 'Developer'
""")

dev_perms = [row['code'] for row in cur.fetchall()]

expected_perms = [
    'projects.create',
    'projects.delete',
    'projects.view',
    'projects.edit',
    'tasks.view'
]

print("\nExpected Developer permissions:")
for perm in expected_perms:
    status = "✓" if perm in dev_perms else "✗"
    print(f"  {status} {perm}")

if dev_perms:
    print("\nActual Developer permissions:")
    for perm in dev_perms:
        print(f"  • {perm}")
else:
    print("\n⚠️ Developer role has NO permissions assigned!")

# Check Vishal's effective permissions
print("\n" + "="*60)
print("CHECKING VISHAL'S EFFECTIVE PERMISSIONS")
print("="*60)

cur.execute("""
    SELECT DISTINCT p.code
    FROM project_role_assignments pra
    JOIN roles r ON pra.role_id = r.id
    JOIN role_permissions rp ON r.id = rp.role_id
    JOIN permissions p ON rp.permission_id = p.id
    JOIN users u ON pra.member_id = u.id
    WHERE u.email = 'vishal@simplyfyd.com'
""")

vishal_perms = [row['code'] for row in cur.fetchall()]

if vishal_perms:
    print(f"\nVishal has {len(vishal_perms)} permissions:")
    for perm in sorted(vishal_perms):
        print(f"  ✓ {perm}")
else:
    print("\n⚠️ Vishal has NO effective permissions!")
    print("This could mean:")
    print("  1. Developer role has no permissions assigned")
    print("  2. Vishal is not assigned to any role")

cur.close()
conn.close()

print("\n" + "="*60)
