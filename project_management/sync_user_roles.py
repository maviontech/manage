#!/usr/bin/env python
"""Sync users.role column with project_role_assignments table"""

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

print("\n" + "="*60)
print("SYNCING users.role COLUMN WITH RBAC ASSIGNMENTS")
print("="*60)

# Get all users
cur.execute("SELECT id, email, full_name, role FROM users")
users = cur.fetchall()

print("\n--- Before Sync ---")
for user in users:
    print(f"  {user['email']:30s} → role: {user['role']}")

# Update each user's role based on their project_role_assignments
for user in users:
    user_id = user['id']
    
    # Get the first role assigned to this user
    cur.execute("""
        SELECT r.name 
        FROM project_role_assignments pra
        JOIN roles r ON pra.role_id = r.id
        WHERE pra.member_id = %s
        LIMIT 1
    """, (user_id,))
    
    role_row = cur.fetchone()
    
    if role_row:
        role_name = role_row['name']
        # Update users.role column
        cur.execute("UPDATE users SET role=%s WHERE id=%s", (role_name, user_id))
        print(f"\n✓ Updated {user['email']} → {role_name}")
    else:
        # No role assigned, keep as NULL (unless it's admin)
        if user['role'] != 'Admin':
            cur.execute("UPDATE users SET role=NULL WHERE id=%s", (user_id,))
            print(f"\n○ {user['email']} → NULL (no role assigned)")

conn.commit()

# Show results
print("\n--- After Sync ---")
cur.execute("SELECT id, email, full_name, role FROM users")
users = cur.fetchall()
for user in users:
    print(f"  {user['email']:30s} → role: {user['role']}")

print("\n" + "="*60)
print("SYNC COMPLETE!")
print("="*60)

cur.close()
conn.close()
