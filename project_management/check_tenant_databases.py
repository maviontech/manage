#!/usr/bin/env python
"""Check what tenant databases exist"""

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

# Get all tenants
cur.execute("SELECT id, client_name, db_name, db_user FROM clients_master ORDER BY id")
tenants = cur.fetchall()

print("\n=== AVAILABLE TENANT DATABASES ===")
print("=" * 70)
for tenant in tenants:
    print(f"ID: {tenant['id']}")
    print(f"  Client Name: {tenant['client_name']}")
    print(f"  Database: {tenant['db_name']}")
    print(f"  DB User: {tenant['db_user']}")
    print()

cur.close()
conn.close()
