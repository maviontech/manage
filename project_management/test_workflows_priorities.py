#!/usr/bin/env python
"""
Test script to verify workflows and priorities pages work correctly
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from core.views_workflows import workflows_view, priorities_view

def add_session_to_request(request):
    """Add session to request"""
    middleware = SessionMiddleware(lambda x: None)
    middleware.process_request(request)
    request.session.save()
    return request

def test_workflows_view():
    """Test workflows view"""
    print("Testing workflows view...")
    factory = RequestFactory()
    request = factory.get('/workflows/')
    request = add_session_to_request(request)
    
    # Add required session data
    request.session['tenant_config'] = {
        'tenant_id': 1,
        'db_name': 'test_db',
        'db_user': 'test_user',
        'db_password': 'test_pass',
        'db_host': '127.0.0.1',
        'db_port': 3306
    }
    request.session['member_id'] = 1
    
    try:
        response = workflows_view(request)
        print(f"✓ Workflows view returned status: {response.status_code}")
        return True
    except Exception as e:
        print(f"✗ Workflows view error: {e}")
        return False

def test_priorities_view():
    """Test priorities view"""
    print("Testing priorities view...")
    factory = RequestFactory()
    request = factory.get('/priorities/')
    request = add_session_to_request(request)
    
    # Add required session data
    request.session['tenant_config'] = {
        'tenant_id': 1,
        'db_name': 'test_db',
        'db_user': 'test_user',
        'db_password': 'test_pass',
        'db_host': '127.0.0.1',
        'db_port': 3306
    }
    request.session['member_id'] = 1
    
    try:
        response = priorities_view(request)
        print(f"✓ Priorities view returned status: {response.status_code}")
        return True
    except Exception as e:
        print(f"✗ Priorities view error: {e}")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("Testing Workflows and Priorities Pages")
    print("=" * 60)
    
    workflows_ok = test_workflows_view()
    priorities_ok = test_priorities_view()
    
    print("\n" + "=" * 60)
    print("Test Results:")
    print("=" * 60)
    print(f"Workflows View: {'✓ PASS' if workflows_ok else '✗ FAIL'}")
    print(f"Priorities View: {'✓ PASS' if priorities_ok else '✗ FAIL'}")
    print("=" * 60)
    
    if workflows_ok and priorities_ok:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed!")
        sys.exit(1)
