"""
Quick test to verify project work type configuration is working
"""
import os
import sys
import django
import logging

logger = logging.getLogger('project_management')

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')
django.setup()

from django.test import RequestFactory
from core.views_tasks import api_get_project_work_types

def test_work_type_api():
    """Test the work type API endpoint"""
    logger.info("\n=== Testing Project Work Type Configuration ===\n")
    
    factory = RequestFactory()
    
    # Test with no project_id
    logger.info("1. Testing with no project_id...")
    request = factory.get('/tasks/api/project-work-types/')
    request.session = {'tenant_db': 'db.sqlite3'}
    response = api_get_project_work_types(request)
    logger.info(f"   Response: {response.content.decode()}")
    
    # Test with a project_id (assuming project 1 exists)
    logger.info("\n2. Testing with project_id=1...")
    request = factory.get('/tasks/api/project-work-types/?project_id=1')
    request.session = {'tenant_db': 'db.sqlite3'}
    response = api_get_project_work_types(request)
    logger.info(f"   Response: {response.content.decode()}")
    
    logger.info("\n=== Test Complete ===\n")
    logger.info("Instructions:")
    logger.info("1. Go to Projects > Click on a project > Configure")
    logger.info("2. Select work types (Bug, Story, Defect, etc.)")
    logger.info("3. Save configuration")
    logger.info("4. Create a task for that project")
    logger.info("5. Work Type dropdown will only show selected types!")

if __name__ == '__main__':
    test_work_type_api()
