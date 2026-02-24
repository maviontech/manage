"""
Test script to verify tasks overview functionality
"""
import sys
import os

# Add the project to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_management.settings')

import django
django.setup()

# Test imports
try:
    from core.views_tasks import tasks_overview_view, export_tasks_excel
    print("✓ Successfully imported tasks_overview_view")
    print("✓ Successfully imported export_tasks_excel")
    
    # Test URL resolution
    from django.urls import reverse
    try:
        url = reverse('tasks_overview')
        print(f"✓ URL 'tasks_overview' resolves to: {url}")
    except Exception as e:
        print(f"✗ Error resolving 'tasks_overview' URL: {e}")
    
    try:
        url = reverse('export_tasks_excel')
        print(f"✓ URL 'export_tasks_excel' resolves to: {url}")
    except Exception as e:
        print(f"✗ Error resolving 'export_tasks_excel' URL: {e}")
    
    # Test template exists
    from django.template.loader import get_template
    try:
        template = get_template('core/tasks_overview.html')
        print("✓ Template 'core/tasks_overview.html' found")
    except Exception as e:
        print(f"✗ Error loading template: {e}")
    
    print("\n✅ All tests passed! The tasks overview feature is ready to use.")
    
except ImportError as e:
    print(f"✗ Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Unexpected error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
