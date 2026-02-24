#!/usr/bin/env python
"""
Setup script to assign Admin role to the first user in a tenant database.
This script should be run after creating the first user account.

Usage:
    python setup_admin.py <email>
    python setup_admin.py admin@company.com
"""
import sys
import os
import pymysql

# Add Django project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')

import django
django.setup()


def setup_admin(email):
    """Assign Admin role to a user by email."""
    
    # Get database connection details from environment
    host = os.environ.get('MYSQL_ADMIN_HOST', '127.0.0.1')
    port = int(os.environ.get('MYSQL_ADMIN_PORT', 3306))
    user = os.environ.get('MYSQL_ADMIN_USER', 'root')
    password = os.environ.get('MYSQL_ADMIN_PWD', 'root')
    master_db = os.environ.get('MASTER_DB_NAME', 'master_db')
    
    try:
        # Connect to master database
        print(f"Connecting to master database: {master_db}")
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=master_db,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )
        cur = conn.cursor()
        
        # Find tenant database from email domain
        domain = email.split('@')[1] if '@' in email else None
        if not domain:
            print(f"ERROR: Invalid email format: {email}")
            return False
        
        print(f"Looking for tenant with domain: @{domain}")
        cur.execute(
            "SELECT db_name, db_user, db_password FROM clients_master WHERE domain_postfix = %s",
            ('@' + domain,)
        )
        tenant = cur.fetchone()
        
        if not tenant:
            print(f"ERROR: No tenant found for domain: @{domain}")
            print("\nAvailable tenants:")
            cur.execute("SELECT client_name, domain_postfix FROM clients_master")
            for t in cur.fetchall():
                print(f"  - {t['client_name']}: {t['domain_postfix']}")
            return False
        
        tenant_db = tenant['db_name']
        tenant_user = tenant['db_user']
        tenant_pwd = tenant['db_password']
        
        print(f"Found tenant database: {tenant_db}")
        
        cur.close()
        conn.close()
        
        # Connect to tenant database
        print(f"Connecting to tenant database: {tenant_db}")
        tenant_conn = pymysql.connect(
            host=host,
            port=port,
            user=tenant_user,
            password=tenant_pwd,
            database=tenant_db,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )
        tenant_cur = tenant_conn.cursor()
        
        # Find member by email
        print(f"Looking for member: {email}")
        tenant_cur.execute("SELECT id, first_name, last_name FROM members WHERE email = %s", (email,))
        member = tenant_cur.fetchone()
        
        if not member:
            print(f"ERROR: Member not found: {email}")
            print("\nAvailable members:")
            tenant_cur.execute("SELECT email, first_name, last_name FROM members LIMIT 10")
            for m in tenant_cur.fetchall():
                print(f"  - {m['email']} ({m['first_name']} {m['last_name']})")
            return False
        
        member_id = member['id']
        member_name = f"{member['first_name']} {member['last_name']}"
        print(f"Found member: {member_name} (ID: {member_id})")
        
        # Find Admin role
        tenant_cur.execute("SELECT id FROM roles WHERE name = 'Admin'")
        admin_role = tenant_cur.fetchone()
        
        if not admin_role:
            print("ERROR: Admin role not found in database")
            print("Please run database initialization first")
            return False
        
        role_id = admin_role['id']
        print(f"Found Admin role (ID: {role_id})")
        
        # Check if already assigned
        tenant_cur.execute("""
            SELECT COUNT(*) as count FROM tenant_role_assignments
            WHERE member_id = %s AND role_id = %s
        """, (member_id, role_id))
        
        if tenant_cur.fetchone()['count'] > 0:
            print(f"\n✓ {member_name} already has Admin role")
            return True
        
        # Assign Admin role (tenant-wide)
        print(f"Assigning Admin role to {member_name}...")
        tenant_cur.execute("""
            INSERT INTO tenant_role_assignments (member_id, role_id, assigned_by)
            VALUES (%s, %s, %s)
        """, (member_id, role_id, member_id))
        
        print(f"\n✓ Successfully assigned Admin role to {member_name}")
        print(f"\nNext steps:")
        print(f"1. Login as {email}")
        print(f"2. Go to Settings → Roles & Permissions to configure roles")
        print(f"3. Go to Settings → Access Control to assign roles to other users")
        
        tenant_cur.close()
        tenant_conn.close()
        
        return True
        
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python setup_admin.py <email>")
        print("Example: python setup_admin.py admin@company.com")
        sys.exit(1)
    
    email = sys.argv[1]
    success = setup_admin(email)
    sys.exit(0 if success else 1)
