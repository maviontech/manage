#!/usr/bin/env python
"""Check Vishal's role assignments"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
django.setup()

import pymysql

# Connect to master database
conn = pymysql.connect(
    host='127.0.0.1',
    port=3306,
    user='root',
    password='root',
    database='master_db',
    cursorclass=pymysql.cursors.DictCursor
)

cur = conn.cursor()

# Get tenant 2 info
cur.execute("SELECT * FROM clients_master WHERE id = 2")
tenant = cur.fetchone()
print(f"\n=== TENANT INFO ===")
print(f"Tenant: {tenant['client_name']}")
print(f"Database: {tenant['db_name']}")

# Switch to tenant database
cur.execute(f"USE {tenant['db_name']}")

print(f"\n=== USERS IN {tenant['db_name']} ===")
cur.execute("SELECT id, email, full_name, role FROM users")
users = cur.fetchall()
for user in users:
    print(f"ID: {user['id']}, Email: {user['email']}, Role Column: {user['role']}")

print(f"\n=== ROLES TABLE ===")
cur.execute("SELECT * FROM roles")
roles = cur.fetchall()
for role in roles:
    print(f"ID: {role['id']}, Name: {role['name']}, Scope: {role.get('scope', 'N/A')}")

print(f"\n=== PROJECT_ROLE_ASSIGNMENTS ===")
cur.execute("""
    SELECT 
        pra.id,
        pra.project_id,
        pra.member_id,
        pra.role_id,
        p.name as project_name,
        u.email as member_email,
        r.name as role_name,
        pra.assigned_at
    FROM project_role_assignments pra
    LEFT JOIN projects p ON pra.project_id = p.id
    LEFT JOIN users u ON pra.member_id = u.id
    LEFT JOIN roles r ON pra.role_id = r.id
    ORDER BY pra.assigned_at DESC
""")
assignments = cur.fetchall()
if assignments:
    for assign in assignments:
        print(f"  Project: {assign['project_name']}, Member: {assign['member_email']}, Role: {assign['role_name']}, Assigned: {assign['assigned_at']}")
else:
    print("  No assignments found!")

print(f"\n=== CHECKING VISHAL SPECIFICALLY ===")
cur.execute("SELECT * FROM users WHERE email LIKE '%vishal%'")
vishal = cur.fetchone()
if vishal:
    print(f"Vishal ID: {vishal['id']}")
    print(f"Email: {vishal['email']}")
    print(f"Role column value: {vishal['role']}")
    
    cur.execute("""
        SELECT 
            pra.*,
            p.name as project_name,
            r.name as role_name
        FROM project_role_assignments pra
        LEFT JOIN projects p ON pra.project_id = p.id
        LEFT JOIN roles r ON pra.role_id = r.id
        WHERE pra.member_id = %s
    """, (vishal['id'],))
    vishal_assignments = cur.fetchall()
    print(f"\nVishal's Project Role Assignments: {len(vishal_assignments)}")
    for assign in vishal_assignments:
        print(f"  - Project: {assign['project_name']}, Role: {assign['role_name']}, Role ID: {assign['role_id']}")

print(f"\n=== UNDERSTANDING THE ISSUE ===")
print("The 'role' column in users table is separate from project_role_assignments.")
print("Your RBAC system uses project_role_assignments table (correct approach).")
print("The 'role' column in users table appears to be legacy/unused.")

cur.close()
conn.close()
