#!/usr/bin/env python3
"""
Add comprehensive permissions for all application features
This script adds permissions for dashboard, time tracking, teams, employees, reports, etc.
"""

import pymysql
import sys
import os

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
import django
django.setup()

from django.conf import settings

def add_comprehensive_permissions():
    """Add all missing permissions to the database"""
    
    # Connect to master database first to get tenant info
    master_conn = pymysql.connect(
        host='localhost',
        user='root',
        password='root',
        database='master_db',
        cursorclass=pymysql.cursors.DictCursor
    )
    
    master_cur = master_conn.cursor()
    
    # Get all tenants
    master_cur.execute("SELECT id, client_name, db_name, db_user, db_password FROM clients_master ORDER BY id")
    tenants = master_cur.fetchall()
    
    master_cur.close()
    master_conn.close()
    
    if not tenants:
        print("❌ No tenants found in master database!")
        return
    
    print(f"\n=== Found {len(tenants)} tenant(s) ===")
    for tenant in tenants:
        print(f"  • {tenant['client_name']} ({tenant['db_name']})")
    
    # Process each tenant
    for tenant in tenants:
        print(f"\n{'=' * 70}")
        print(f"Processing Tenant: {tenant['client_name']}")
        print(f"Database: {tenant['db_name']}")
        print(f"{'=' * 70}")
        
        # Connect to tenant database
        conn = pymysql.connect(
            host='localhost',
            user='root',
            password='root',
            database=tenant['db_name'],
            cursorclass=pymysql.cursors.DictCursor
        )
        
        cur = conn.cursor()
        
        # Define comprehensive permissions
        permissions = [
            # Dashboard
            ('dashboard.view', 'View dashboard'),
            
            # Projects (additional)
            ('projects.view_all', 'View all projects'),
            ('projects.configure', 'Configure project settings'),
            
            # Tasks (additional)
            ('tasks.view_unassigned', 'View unassigned tasks'),
            ('tasks.create_unassigned', 'Create unassigned tasks'),
            ('tasks.bulk_import', 'Bulk import tasks via CSV'),
            ('tasks.view_board', 'View task board'),
            ('tasks.view_analytics', 'View task analytics'),
            ('tasks.export', 'Export tasks'),
            ('tasks.assign_unassigned', 'Assign unassigned tasks'),
            ('tasks.manage_board', 'Manage task board'),
        
        # Time Tracking
        ('time.view', 'View time entries'),
        ('time.record', 'Record time (start/stop timer)'),
        ('time.edit', 'Edit time entries'),
        ('time.delete', 'Delete time entries'),
        ('time.approve', 'Approve time entries'),
        ('time.view_all', 'View all time entries'),
        
        # Teams & People
        ('teams.view', 'View teams'),
        ('teams.create', 'Create teams'),
        ('teams.edit', 'Edit teams'),
        ('teams.delete', 'Delete teams'),
        ('teams.manage_members', 'Manage team members'),
        
        ('people.view', 'View people'),
        ('people.invite', 'Invite people'),
            ('people.edit', 'Edit people'),
            ('people.delete', 'Delete people'),
            
            # Employees
            ('employees.view', 'View employees'),
            ('employees.create', 'Create employees'),
            ('employees.edit', 'Edit employees'),
            ('employees.delete', 'Delete employees'),
            
            # Members (additional)
            ('members.view', 'View members'),
            ('members.invite', 'Invite members'),
            ('members.edit', 'Edit members'),
            ('members.delete', 'Delete members'),
            ('members.manage_roles', 'Manage member roles'),
            
            # Reports
            ('reports.view', 'View reports'),
            ('reports.create', 'Create reports'),
            ('reports.edit', 'Edit reports'),
            ('reports.delete', 'Delete reports'),
            ('reports.export', 'Export reports'),
            ('reports.view_projects', 'View project reports'),
            
            # Notifications
            ('notifications.view', 'View notifications'),
            ('notifications.manage', 'Manage notifications'),
            
            # Settings
            ('settings.view', 'View settings'),
            ('settings.edit', 'Edit settings'),
            ('settings.password_policy', 'Manage password policy'),
            
            # Roles & Permissions
            ('roles.view', 'View roles'),
            ('roles.create', 'Create roles'),
            ('roles.edit', 'Edit roles'),
            ('roles.delete', 'Delete roles'),
            ('roles.manage', 'Manage roles and permissions'),
            ('roles.assign', 'Assign roles to users'),
            ('permissions.view', 'View permissions'),
            ('permissions.manage', 'Manage permissions'),
            
            # Admin
            ('admin.access', 'Access admin panel'),
            ('admin.view_logs', 'View system logs'),
            ('admin.manage_tenants', 'Manage tenants'),
        ]
        
        print("Adding comprehensive permissions...")
        print("=" * 70)
        
        added_count = 0
        existing_count = 0
        
        for code, description in permissions:
            # Check if permission already exists
            cur.execute("SELECT id FROM permissions WHERE code = %s", (code,))
            existing = cur.fetchone()
            
            if existing:
                print(f"✓ Already exists: {code}")
                existing_count += 1
            else:
                cur.execute(
                    "INSERT INTO permissions (code, description) VALUES (%s, %s)",
                    (code, description)
                )
                print(f"✅ Added: {code} - {description}")
                added_count += 1
        
        conn.commit()
        
        print("\n" + "=" * 70)
        print(f"Summary for {tenant['client_name']}:")
        print(f"  Added: {added_count} new permissions")
        print(f"  Existing: {existing_count} permissions")
        print(f"  Total: {added_count + existing_count} permissions")
        
        # Show all permissions grouped by category
        print("\n" + "=" * 70)
        print("All Permissions by Category:")
        print("=" * 70)
        
        cur.execute("SELECT code, description FROM permissions ORDER BY code")
        all_perms = cur.fetchall()
        
        categories = {}
        for perm in all_perms:
            category = perm['code'].split('.')[0]
            if category not in categories:
                categories[category] = []
            categories[category].append(perm)
        
        for category, perms in sorted(categories.items()):
            print(f"\n{category.upper()}:")
            for perm in perms:
                print(f"  • {perm['code']:<30} - {perm['description']}")
        
        # Update default role permissions
        print("\n" + "=" * 70)
        print("Updating Default Role Permissions:")
        print("=" * 70)
        
        # Get role IDs
        cur.execute("SELECT id, name FROM roles")
        roles = {row['name']: row['id'] for row in cur.fetchall()}
        
        # Define role permission mappings
        role_permissions = {
            'Admin': [
                # Admin gets EVERYTHING
                'dashboard.view',
                'projects.view', 'projects.view_all', 'projects.create', 'projects.edit', 'projects.delete', 'projects.configure',
                'tasks.view', 'tasks.create', 'tasks.edit', 'tasks.delete', 'tasks.assign',
                'tasks.view_unassigned', 'tasks.create_unassigned', 'tasks.assign_unassigned', 'tasks.bulk_import', 
                'tasks.view_board', 'tasks.manage_board', 'tasks.view_analytics', 'tasks.export',
                'time.view', 'time.record', 'time.edit', 'time.delete', 'time.approve', 'time.view_all',
                'teams.view', 'teams.create', 'teams.edit', 'teams.delete', 'teams.manage_members',
                'people.view', 'people.invite', 'people.edit', 'people.delete',
                'employees.view', 'employees.create', 'employees.edit', 'employees.delete',
                'members.view', 'members.invite', 'members.edit', 'members.delete', 'members.manage_roles',
                'reports.view', 'reports.create', 'reports.edit', 'reports.delete', 'reports.export', 'reports.view_projects',
                'notifications.view', 'notifications.manage',
                'settings.view', 'settings.edit', 'settings.password_policy',
                'roles.view', 'roles.create', 'roles.edit', 'roles.delete', 'roles.manage', 'roles.assign',
                'permissions.view', 'permissions.manage',
                'admin.access', 'admin.view_logs', 'admin.manage_tenants',
            ],
            'Developer': [
                'dashboard.view',
                'projects.view', 'projects.edit',
                'tasks.view', 'tasks.create', 'tasks.edit', 'tasks.view_unassigned', 'tasks.view_board', 'tasks.view_analytics',
                'time.view', 'time.record',
                'teams.view',
                'people.view',
                'reports.view',
                'notifications.view',
                'roles.view',
            ],
            'Tester': [
                'dashboard.view',
                'projects.view',
                'tasks.view', 'tasks.create', 'tasks.edit', 'tasks.assign', 'tasks.view_unassigned', 'tasks.view_board', 'tasks.view_analytics',
                'time.view', 'time.record',
                'teams.view',
                'people.view',
                'reports.view',
                'notifications.view',
                'roles.view',
            ],
            'Collaborator': [
                'dashboard.view',
                'projects.view',
                'tasks.view', 'tasks.create', 'tasks.view_board',
                'time.view', 'time.record',
                'teams.view',
                'people.view',
                'notifications.view',
            ],
            'Viewer': [
                'dashboard.view',
                'projects.view',
                'tasks.view', 'tasks.view_board', 'tasks.view_analytics',
                'teams.view',
                'people.view',
                'reports.view',
                'notifications.view',
                'roles.view',
            ],
        }
        
        for role_name, perm_codes in role_permissions.items():
            if role_name not in roles:
                print(f"⚠️  Role '{role_name}' not found, skipping...")
                continue
            
            role_id = roles[role_name]
            print(f"\n{role_name}:")
            
            # Clear existing permissions for this role
            cur.execute("DELETE FROM role_permissions WHERE role_id = %s", (role_id,))
            
            # Add new permissions
            for perm_code in perm_codes:
                cur.execute("SELECT id FROM permissions WHERE code = %s", (perm_code,))
                perm = cur.fetchone()
                if perm:
                    cur.execute(
                        "INSERT INTO role_permissions (role_id, permission_id) VALUES (%s, %s)",
                        (role_id, perm['id'])
                    )
                    print(f"  ✓ {perm_code}")
                else:
                    print(f"  ⚠️  Permission not found: {perm_code}")
        
        conn.commit()
        
        print("\n" + "=" * 70)
        print(f"✅ Comprehensive permissions added successfully for {tenant['client_name']}!")
    print("=" * 70)
    
    cur.close()
    conn.close()
    
    print("\n" + "=" * 70)
    print("✅ ALL TENANTS PROCESSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == '__main__':
    try:
        add_comprehensive_permissions()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
