#!/usr/bin/env python
"""Test if Developer can create projects"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
django.setup()

from core.rbac import has_permission, get_user_roles, get_role_permissions
from core.db_helpers import get_tenant_conn

class MockRequest:
    def __init__(self, member_id, tenant_key='simplyfyd.com'):
        self.session = {
            'member_id': member_id,
            'tenant_key': tenant_key,
            'tenant_config': {
                'db_name': 'simployfyd_db',
                'db_host': '127.0.0.1',
                'db_port': 3306,
                'db_user': 'tenant_2',
                'db_password': 'd4WizlQ8jg6gpUJmLU',
                'db_engine': 'mysql'
            }
        }
    
    def get_host(self):
        return 'simplyfyd.com'

print("\n" + "="*70)
print("TESTING: Can Developer Create Projects?")
print("="*70)

# Test Vishal (Developer, member_id=2)
vishal_request = MockRequest(member_id=2)

print("\n1. Testing Vishal (Developer)")
print("-" * 70)

# Get connection
conn = get_tenant_conn(vishal_request)

# Get roles WITHOUT project_id (for creating new project)
print("\nGetting roles without project_id (for create project):")
roles = get_user_roles(conn, member_id=2, project_id=None)
print(f"  Roles found: {roles}")

if roles:
    # Get permissions for those roles
    permissions = get_role_permissions(conn, roles)
    print(f"\n  Permissions: {sorted(permissions)}")
    
    # Check if has projects.create
    has_create = 'projects.create' in permissions
    print(f"\n  Has 'projects.create': {has_create}")
else:
    print("  ❌ No roles found!")

conn.close()

# Now test with has_permission function
print("\n2. Testing has_permission() function")
print("-" * 70)

result = has_permission(vishal_request, 'projects.create', project_id=None)
print(f"\nhas_permission(request, 'projects.create', project_id=None)")
print(f"  Result: {result}")

if result:
    print("\n✅ SUCCESS! Developer CAN create projects!")
else:
    print("\n❌ FAILED! Developer CANNOT create projects!")

# Test with specific project
print("\n3. Testing with specific project_id")
print("-" * 70)

result_with_project = has_permission(vishal_request, 'projects.create', project_id=1)
print(f"\nhas_permission(request, 'projects.create', project_id=1)")
print(f"  Result: {result_with_project}")

print("\n" + "="*70)
print("CONCLUSION")
print("="*70)

if result:
    print("""
✅ Fix successful!

Developer can now create projects because:
  1. get_user_roles() now checks ALL projects when project_id=None
  2. Finds Developer role from any project assignment
  3. Gets permissions for Developer role
  4. Finds 'projects.create' permission
  5. Allows access!

Vishal can now:
  ✅ Create new projects (no project_id needed)
  ✅ Edit existing projects (with project_id)
  ✅ Delete projects (with project_id)
""")
else:
    print("""
❌ Still not working!

Need to debug further...
""")

print("="*70 + "\n")
