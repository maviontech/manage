import pymysql
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
django.setup()

from django.conf import settings

# Connect to MySQL admin
conn = pymysql.connect(
    host=settings.MYSQL_ADMIN_HOST,
    port=settings.MYSQL_ADMIN_PORT,
    user=settings.MYSQL_ADMIN_USER,
    password=settings.MYSQL_ADMIN_PWD,
    cursorclass=pymysql.cursors.DictCursor
)

cur = conn.cursor()

# Get all databases
cur.execute("SHOW DATABASES")
databases = cur.fetchall()

print("All databases:")
for db in databases:
    print(f"  - {db['Database']}")

# Check master_db for tenants
cur.execute("USE master_db")
cur.execute("SHOW TABLES")
tables = cur.fetchall()

print("\nTables in master_db:")
for table in tables:
    print(f"  - {list(table.values())[0]}")

# Check if tenants table exists
cur.execute("SHOW TABLES LIKE 'tenants'")
if cur.fetchone():
    cur.execute("SELECT id, name, db_name FROM tenants")
    tenants = cur.fetchall()
    print("\nTenants:")
    for tenant in tenants:
        print(f"  - ID: {tenant['id']}, Name: {tenant['name']}, DB: {tenant['db_name']}")

cur.close()
conn.close()
