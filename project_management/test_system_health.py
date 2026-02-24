#!/usr/bin/env python
"""
System Health Check Script
Tests all critical components of the Django application
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
django.setup()

from django.urls import get_resolver
from django.conf import settings
from core import rbac, views_permissions, views_tasks, views_workweek

def test_imports():
    """Test critical module imports"""
    print("\n=== Testing Module Imports ===")
    
    tests = [
        ("RBAC Module", lambda: hasattr(rbac, 'has_permission')),
        ("Permissions Views", lambda: hasattr(views_permissions, 'access_control_page')),
        ("Task Views", lambda: hasattr(views_tasks, 'create_task_view')),
        ("Work Week Views", lambda: hasattr(views_workweek, 'work_week_view')),
    ]
    
    passed = 0
    for name, test_func in tests:
        try:
            if test_func():
                print(f"✓ {name}: OK")
                passed += 1
            else:
                print(f"✗ {name}: FAILED - Missing expected function")
        except Exception as e:
            print(f"✗ {name}: ERROR - {e}")
    
    return passed, len(tests)

def test_url_routing():
    """Test URL routing configuration"""
    print("\n=== Testing URL Routing ===")
    
    resolver = get_resolver()
    url_patterns = []
    
    def collect_patterns(patterns, prefix=''):
        for pattern in patterns:
            if hasattr(pattern, 'url_patterns'):
                collect_patterns(pattern.url_patterns, prefix + str(pattern.pattern))
            else:
                url_patterns.append(prefix + str(pattern.pattern))
    
    collect_patterns(resolver.url_patterns)
    
    print(f"✓ Total URL patterns registered: {len(url_patterns)}")
    
    # Test critical URLs
    critical_urls = [
        'dashboard/',
        'tasks/board/',
        'settings/access-control/',
        'settings/roles/',
        'tasks/work-week/',
    ]
    
    found = 0
    for url in critical_urls:
        if any(url in pattern for pattern in url_patterns):
            print(f"✓ Critical URL found: {url}")
            found += 1
        else:
            print(f"✗ Critical URL missing: {url}")
    
    return found, len(critical_urls)

def test_database_connection():
    """Test database connectivity"""
    print("\n=== Testing Database Connection ===")
    
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            if result == (1,):
                print("✓ Database connection: OK")
                return 1, 1
            else:
                print("✗ Database connection: Unexpected result")
                return 0, 1
    except Exception as e:
        print(f"✗ Database connection: ERROR - {e}")
        return 0, 1

def test_settings():
    """Test Django settings"""
    print("\n=== Testing Django Settings ===")
    
    checks = [
        ("DEBUG mode", settings.DEBUG),
        ("INSTALLED_APPS", len(settings.INSTALLED_APPS) > 0),
        ("MIDDLEWARE", len(settings.MIDDLEWARE) > 0),
        ("TEMPLATES", len(settings.TEMPLATES) > 0),
    ]
    
    passed = 0
    for name, condition in checks:
        if condition:
            print(f"✓ {name}: OK")
            passed += 1
        else:
            print(f"✗ {name}: FAILED")
    
    return passed, len(checks)

def test_rbac_functions():
    """Test RBAC function availability"""
    print("\n=== Testing RBAC Functions ===")
    
    functions = [
        'get_user_roles',
        'get_role_permissions',
        'has_permission',
        'get_user_permissions',
        'require_permission',
        'is_admin',
        'get_accessible_projects',
        'check_project_access',
        'assign_role_to_user',
        'remove_role_from_user',
    ]
    
    passed = 0
    for func_name in functions:
        if hasattr(rbac, func_name):
            print(f"✓ {func_name}: Available")
            passed += 1
        else:
            print(f"✗ {func_name}: Missing")
    
    return passed, len(functions)

def main():
    """Run all tests and generate report"""
    print("=" * 60)
    print("SYSTEM HEALTH CHECK")
    print("=" * 60)
    
    results = []
    
    # Run all tests
    results.append(("Module Imports", *test_imports()))
    results.append(("URL Routing", *test_url_routing()))
    results.append(("Database Connection", *test_database_connection()))
    results.append(("Django Settings", *test_settings()))
    results.append(("RBAC Functions", *test_rbac_functions()))
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    total_passed = 0
    total_tests = 0
    
    for name, passed, total in results:
        total_passed += passed
        total_tests += total
        status = "✓ PASS" if passed == total else "✗ FAIL"
        print(f"{status} {name}: {passed}/{total}")
    
    print("\n" + "=" * 60)
    success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
    print(f"OVERALL: {total_passed}/{total_tests} tests passed ({success_rate:.1f}%)")
    print("=" * 60)
    
    return 0 if total_passed == total_tests else 1

if __name__ == '__main__':
    sys.exit(main())
