#!/usr/bin/env python
"""Test profile role display"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
django.setup()

import pymysql

# Connect to tenant database
conn = pymysql.connect(
    host='127.0.0.1',
    port=3306,
    user='root',
    password='root',
    database='simployfyd_db',
    cursorclass=pymysql.cursors.DictCursor
)

cur = conn.cursor()

print("\n=== TESTING PROFILE ROLE DISPLAY ===\n")

# Get Vishal's member ID
cur.execute("SELECT id, email, first_name, last_name FROM members WHERE email LIKE '%vishal%'")
vishal = cur.fetchone()

if vishal:
    member_id = vishal['id']
    print(f"User: {vishal['first_name']} {vishal['last_name']}")
    print(f"Email: {vishal['email']}")
    print(f"Member ID: {member_id}")
    
    # Fetch roles (same query as profile_view)
    print("\n--- Project Roles ---")
    cur.execute("""
        SELECT DISTINCT r.name, p.name as project_name, pra.assigned_at
        FROM project_role_assignments pra
        JOIN roles r ON pra.role_id = r.id
        LEFT JOIN projects p ON pra.project_id = p.id
        WHERE pra.member_id = %s
        ORDER BY pra.assigned_at DESC
    """, (member_id,))
    
    project_roles = cur.fetchall()
    if project_roles:
        for role in project_roles:
            print(f"  ✓ {role['name']} - {role['project_name']}")
    else:
        print("  No project roles found")
    
    # Check tenant-wide roles
    print("\n--- Tenant-wide Roles ---")
    cur.execute("""
        SELECT DISTINCT r.name
        FROM tenant_role_assignments tra
        JOIN roles r ON tra.role_id = r.id
        WHERE tra.member_id = %s
    """, (member_id,))
    
    tenant_roles = cur.fetchall()
    if tenant_roles:
        for role in tenant_roles:
            print(f"  ✓ {role['name']} - Tenant-wide")
    else:
        print("  No tenant-wide roles found")
    
    # Summary
    total_roles = len(project_roles) + len(tenant_roles)
    print(f"\n=== SUMMARY ===")
    print(f"Total roles: {total_roles}")
    
    if total_roles > 0:
        print("\n✅ Roles will now display on profile page!")
        print("\nWhat will show on profile:")
        for role in project_roles:
            print(f"  • {role['name']} - {role['project_name']}")
        for role in tenant_roles:
            print(f"  • {role['name']} - Tenant-wide")
    else:
        print("\n⚠️ No roles assigned yet. Profile will show 'Member' as default.")
else:
    print("❌ Vishal not found in database")

cur.close()
conn.close()
