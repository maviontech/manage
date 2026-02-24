#!/usr/bin/env python3
"""
Test Developer role permissions
Verify that Developer role has correct restricted permissions
"""

import pymysql
import sys
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
import django
django.setup()

def test_developer_permissions():
    """Test Developer role permissions"""
    
    # Connect to tenant database
    conn = pymysql.connect(
        host='localhost',
        user='root',
        password='root',
        database='Maviontech_db_demo',  # Test with first tenant
        cursorclass=pymysql.cursors.DictCursor
    )
    
    cur = conn.cursor()
    
    print("\n" + "=" * 70)
    print("TESTING DEVELOPER ROLE PERMISSIONS")
    print("=" * 70)
    
    # Get Developer role
    cur.execute("SELECT id, name FROM roles WHERE name = 'Developer'")
    role = cur.fetchone()
    
    if not role:
        print("❌ Developer role not found!")
        return
    
    role_id = role['id']
    print(f"\n✓ Found Developer role (ID: {role_id})")
    
    # Get all permissions for Developer role
    cur.execute("""
        SELECT p.code, p.description
        FROM role_permissions rp
        JOIN permissions p ON rp.permission_id = p.id
        WHERE rp.role_id = %s
        ORDER BY p.code
    """, (role_id,))
    
    permissions = cur.fetchall()
    
    print(f"\n{'=' * 70}")
    print(f"DEVELOPER ROLE HAS {len(permissions)} PERMISSIONS:")
    print(f"{'=' * 70}")
    
    for perm in permissions:
        print(f"  ✓ {perm['code']:<30} - {perm['description']}")
    
    # Expected permissions
    expected = [
        'dashboard.view',
        'projects.view',
        'projects.create',
        'tasks.view',
        'tasks.view_unassigned',
        'notifications.view',
    ]
    
    actual = [p['code'] for p in permissions]
    
    print(f"\n{'=' * 70}")
    print("VERIFICATION:")
    print(f"{'=' * 70}")
    
    all_correct = True
    
    # Check expected permissions are present
    for perm in expected:
        if perm in actual:
            print(f"  ✓ {perm} - PRESENT")
        else:
            print(f"  ❌ {perm} - MISSING")
            all_correct = False
    
    # Check for unexpected permissions
    unexpected = [p for p in actual if p not in expected]
    if unexpected:
        print(f"\n⚠️  UNEXPECTED PERMISSIONS FOUND:")
        for perm in unexpected:
            print(f"  ⚠️  {perm}")
        all_correct = False
    
    # Verify Developer DOES NOT have these permissions
    should_not_have = [
        'tasks.create',
        'tasks.edit',
        'tasks.delete',
        'tasks.view_board',
        'tasks.view_analytics',
        'tasks.bulk_import',
        'projects.edit',
        'projects.delete',
        'roles.manage',
        'admin.access',
    ]
    
    print(f"\n{'=' * 70}")
    print("DEVELOPER SHOULD NOT HAVE:")
    print(f"{'=' * 70}")
    
    for perm in should_not_have:
        if perm not in actual:
            print(f"  ✓ {perm} - CORRECTLY DENIED")
        else:
            print(f"  ❌ {perm} - INCORRECTLY GRANTED")
            all_correct = False
    
    print(f"\n{'=' * 70}")
    if all_correct:
        print("✅ ALL TESTS PASSED - Developer role is correctly configured!")
    else:
        print("❌ SOME TESTS FAILED - Developer role needs adjustment!")
    print(f"{'=' * 70}")
    
    # Test what a Developer user can access
    print(f"\n{'=' * 70}")
    print("DEVELOPER CAN ACCESS:")
    print(f"{'=' * 70}")
    print("  ✓ Dashboard")
    print("  ✓ View Projects")
    print("  ✓ Create Projects")
    print("  ✓ My Tasks (view only)")
    print("  ✓ Unassigned Tasks (view only)")
    print("  ✓ Notifications")
    
    print(f"\n{'=' * 70}")
    print("DEVELOPER CANNOT ACCESS:")
    print(f"{'=' * 70}")
    print("  ✗ Create Tasks")
    print("  ✗ Edit Tasks")
    print("  ✗ Delete Tasks")
    print("  ✗ Task Board")
    print("  ✗ Task Analytics")
    print("  ✗ Bulk Import")
    print("  ✗ Edit Projects")
    print("  ✗ Delete Projects")
    print("  ✗ Roles & Permissions Management")
    print("  ✗ Admin Panel")
    
    cur.close()
    conn.close()

if __name__ == '__main__':
    try:
        test_developer_permissions()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
