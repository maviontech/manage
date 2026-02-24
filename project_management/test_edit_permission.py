#!/usr/bin/env python
"""
Test why Vishal cannot edit projects even though Developer role has projects.edit permission
"""
import pymysql
import pymysql.cursors

def test_edit_permission():
    """Test Vishal's edit permission"""
    print("=" * 70)
    print("TESTING VISHAL'S PROJECT EDIT PERMISSION")
    print("=" * 70)
    
    # Connect directly to simployfyd_db
    conn = pymysql.connect(
        host='127.0.0.1',
        port=3306,
        user='root',
        password='root',
        database='simployfyd_db',
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )
    cur = conn.cursor()
    
    try:
        # Get Vishal's member_id
        cur.execute("SELECT id, email FROM users WHERE email='vishal@simplyfyd.com'")
        vishal = cur.fetchone()
        
        if not vishal:
            print("❌ Vishal not found!")
            return
        
        member_id = vishal['id']
        print(f"\n✓ Vishal found: member_id={member_id}, email={vishal['email']}")
        
        # Get Vishal's role assignments
        print("\n" + "=" * 70)
        print("VISHAL'S ROLE ASSIGNMENTS")
        print("=" * 70)
        
        cur.execute("""
            SELECT pra.id, pra.project_id, pra.role_id, 
                   p.name as project_name, r.name as role_name
            FROM project_role_assignments pra
            JOIN projects p ON pra.project_id = p.id
            JOIN roles r ON pra.role_id = r.id
            WHERE pra.member_id = %s
        """, (member_id,))
        
        assignments = cur.fetchall()
        
        if not assignments:
            print("❌ No role assignments found for Vishal!")
            return
        
        for a in assignments:
            print(f"\n✓ Project: {a['project_name']} (ID: {a['project_id']})")
            print(f"  Role: {a['role_name']} (ID: {a['role_id']})")
        
        # Get Developer role permissions
        print("\n" + "=" * 70)
        print("DEVELOPER ROLE PERMISSIONS")
        print("=" * 70)
        
        cur.execute("""
            SELECT p.id, p.code, p.description
            FROM permissions p
            JOIN role_permissions rp ON p.id = rp.permission_id
            WHERE rp.role_id = (SELECT id FROM roles WHERE name='Developer')
            ORDER BY p.code
        """)
        
        permissions = cur.fetchall()
        
        print(f"\nDeveloper role has {len(permissions)} permissions:")
        has_edit = False
        for perm in permissions:
            print(f"  ✓ {perm['code']} - {perm['description']}")
            if perm['code'] == 'projects.edit':
                has_edit = True
        
        if has_edit:
            print("\n✅ Developer role HAS projects.edit permission!")
        else:
            print("\n❌ Developer role DOES NOT have projects.edit permission!")
        
        # Test permission check for specific project
        print("\n" + "=" * 70)
        print("TESTING PERMISSION CHECK WITH PROJECT_ID")
        print("=" * 70)
        
        for a in assignments:
            project_id = a['project_id']
            role_id = a['role_id']
            
            print(f"\nTesting for project_id={project_id} (role_id={role_id}):")
            
            # Simulate get_user_roles with project_id
            cur.execute("""
                SELECT DISTINCT role_id 
                FROM project_role_assignments 
                WHERE member_id=%s AND project_id=%s
            """, (member_id, project_id))
            
            roles_for_project = [row['role_id'] for row in cur.fetchall()]
            print(f"  Roles found for this project: {roles_for_project}")
            
            # Get permissions for these roles
            if roles_for_project:
                placeholders = ','.join(['%s'] * len(roles_for_project))
                cur.execute(f"""
                    SELECT DISTINCT p.code 
                    FROM permissions p
                    JOIN role_permissions rp ON p.id = rp.permission_id
                    WHERE rp.role_id IN ({placeholders})
                """, tuple(roles_for_project))
                
                perms = [row['code'] for row in cur.fetchall()]
                
                if 'projects.edit' in perms:
                    print(f"  ✅ projects.edit permission FOUND for project {project_id}")
                else:
                    print(f"  ❌ projects.edit permission NOT FOUND for project {project_id}")
                    print(f"  Available permissions: {perms}")
        
        # Test permission check WITHOUT project_id (like create)
        print("\n" + "=" * 70)
        print("TESTING PERMISSION CHECK WITHOUT PROJECT_ID")
        print("=" * 70)
        
        # Simulate get_user_roles without project_id
        cur.execute("""
            SELECT DISTINCT role_id 
            FROM project_role_assignments 
            WHERE member_id=%s
        """, (member_id,))
        
        all_roles = [row['role_id'] for row in cur.fetchall()]
        print(f"\nAll roles across all projects: {all_roles}")
        
        if all_roles:
            placeholders = ','.join(['%s'] * len(all_roles))
            cur.execute(f"""
                SELECT DISTINCT p.code 
                FROM permissions p
                JOIN role_permissions rp ON p.id = rp.permission_id
                WHERE rp.role_id IN ({placeholders})
            """, tuple(all_roles))
            
            perms = [row['code'] for row in cur.fetchall()]
            
            if 'projects.edit' in perms:
                print(f"✅ projects.edit permission FOUND (no project_id)")
            else:
                print(f"❌ projects.edit permission NOT FOUND (no project_id)")
            
            print(f"\nAll permissions: {perms}")
        
        # Check the actual URL pattern
        print("\n" + "=" * 70)
        print("CHECKING PROJECT EDIT VIEW")
        print("=" * 70)
        
        print("\nThe project_edit view uses:")
        print("  @require_permission('projects.edit', project_param='project_id')")
        print("\nThis means it will:")
        print("  1. Get project_id from URL kwargs")
        print("  2. Call has_permission(request, 'projects.edit', project_id)")
        print("  3. Check if user has projects.edit for THAT specific project")
        
        print("\n" + "=" * 70)
        print("DIAGNOSIS")
        print("=" * 70)
        
        if has_edit and assignments:
            print("\n✅ Vishal HAS Developer role")
            print("✅ Developer role HAS projects.edit permission")
            print("✅ Vishal is assigned to project(s)")
            print("\n🔍 The permission check SHOULD work!")
            print("\n⚠️  Possible issues:")
            print("   1. Session might have wrong member_id")
            print("   2. Project ID in URL might not match assigned project")
            print("   3. Database connection issue in request")
        else:
            print("\n❌ Problem found in configuration!")
    
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    test_edit_permission()
