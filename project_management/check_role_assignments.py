#!/usr/bin/env python
"""Check role assignments in database"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
django.setup()

from core.db_helpers import get_master_db_connection

def check_database():
    conn = get_master_db_connection()
    cur = conn.cursor(dictionary=True)
    
    print("\n=== CHECKING ROLE TABLES ===\n")
    
    # Check for role-related tables
    cur.execute("SHOW TABLES LIKE '%role%'")
    tables = cur.fetchall()
    print("Role-related tables:")
    for table in tables:
        table_name = list(table.values())[0]
        print(f"  - {table_name}")
    
    print("\n=== CHECKING TENANT 2 (simplyfyd) ===\n")
    
    # Switch to tenant 2 database
    cur.execute("USE tenant_2_db")
    
    # Check roles table
    print("1. Roles defined:")
    cur.execute("SELECT * FROM roles")
    roles = cur.fetchall()
    for role in roles:
        print(f"   ID: {role['id']}, Name: {role['name']}, Scope: {role.get('scope', 'N/A')}")
    
    # Check users
    print("\n2. Users:")
    cur.execute("SELECT id, email, full_name, role FROM users")
    users = cur.fetchall()
    for user in users:
        print(f"   ID: {user['id']}, Email: {user['email']}, Name: {user['full_name']}, Role Column: {user['role']}")
    
    # Check project_role_assignments
    print("\n3. Project Role Assignments:")
    cur.execute("""
        SELECT pra.*, p.name as project_name, u.email as member_email, r.name as role_name
        FROM project_role_assignments pra
        LEFT JOIN projects p ON pra.project_id = p.id
        LEFT JOIN users u ON pra.member_id = u.id
        LEFT JOIN roles r ON pra.role_id = r.id
    """)
    assignments = cur.fetchall()
    if assignments:
        for assign in assignments:
            print(f"   Project: {assign['project_name']}, Member: {assign['member_email']}, Role: {assign['role_name']}")
    else:
        print("   No project role assignments found")
    
    # Check tenant_role_assignments if exists
    print("\n4. Tenant Role Assignments:")
    try:
        cur.execute("""
            SELECT tra.*, u.email as member_email, r.name as role_name
            FROM tenant_role_assignments tra
            LEFT JOIN users u ON tra.member_id = u.id
            LEFT JOIN roles r ON tra.role_id = r.id
        """)
        tenant_assignments = cur.fetchall()
        if tenant_assignments:
            for assign in tenant_assignments:
                print(f"   Member: {assign['member_email']}, Role: {assign['role_name']}")
        else:
            print("   No tenant role assignments found")
    except Exception as e:
        print(f"   Table doesn't exist or error: {e}")
    
    # Check vishal specifically
    print("\n5. Vishal's Details:")
    cur.execute("SELECT * FROM users WHERE email LIKE '%vishal%'")
    vishal = cur.fetchone()
    if vishal:
        print(f"   User ID: {vishal['id']}")
        print(f"   Email: {vishal['email']}")
        print(f"   Full Name: {vishal['full_name']}")
        print(f"   Role Column: {vishal['role']}")
        
        # Check project assignments
        cur.execute("""
            SELECT pra.*, p.name as project_name, r.name as role_name
            FROM project_role_assignments pra
            LEFT JOIN projects p ON pra.project_id = p.id
            LEFT JOIN roles r ON pra.role_id = r.id
            WHERE pra.member_id = %s
        """, (vishal['id'],))
        vishal_roles = cur.fetchall()
        print(f"\n   Project Role Assignments for Vishal:")
        if vishal_roles:
            for role in vishal_roles:
                print(f"     - Project: {role['project_name']}, Role: {role['role_name']}, Role ID: {role['role_id']}")
        else:
            print("     No project roles assigned")
    
    cur.close()
    conn.close()

if __name__ == '__main__':
    check_database()
