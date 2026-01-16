# PROJECT CONFIGURATION FEATURE - JIRA-LIKE SETUP

## Overview
This feature allows organizations to configure their projects similar to Jira, with customizable work types and statuses.

## Workflow

### Step 1: Create Project (Existing Flow)
- Admin creates a project with basic details:
  - Name
  - Description
  - Start Date
  - End Date
  - Status
  - Assigned Employee

### Step 2: Configure Project (NEW - Similar to Jira)
After creating a project, you are redirected to a configuration page where you can:

#### A. Select Work Types (Optional)
Choose which types of work items your project will use:
- ✅ **Task** - A small piece of work
- ✅ **Bug** - A problem that needs fixing
- ✅ **Story** - A requirement expressed from the user's perspective
- ✅ **Defect** - An issue reported in production
- ✅ **Sub Task** - A smaller task within a main task
- ✅ **Report** - Generate reports and analytics
- ✅ **Change Request** - Request for system changes

#### B. Define Statuses (Optional)
Customize the workflow statuses for your project:
- Default: To Do → In Progress → In Review → Done
- You can customize these by entering one status per line

## Database Structure

### New Tables:

1. **project_work_types**
   - Stores which work types are enabled for each project
   - Columns: id, project_id, work_type, is_enabled, created_at

2. **project_statuses**
   - Stores custom statuses for each project
   - Columns: id, project_id, status_name, status_order, created_at

3. **tasks table (modified)**
   - Added column: work_type VARCHAR(50) DEFAULT 'Task'
   - This allows tasks to be categorized by type

## How to Use

### For Project Creators:
1. Navigate to Projects → Create New Project
2. Fill in project details and submit
3. You'll be redirected to the configuration page
4. Select the work types you need (e.g., Task, Bug, Story)
5. Optionally customize statuses (or use defaults)
6. Click "Save Configuration"

### For Task Creators:
When creating tasks for a configured project, you can:
- Select the work_type from the configured options
- Use the custom statuses defined for that project

## URL Routes

- `/projects/` - List all projects
- `/projects/create/` - Create new project (Step 1)
- `/projects/<id>/configure/` - Configure project (Step 2 - NEW)
- `/projects/<id>/edit/` - Edit project details

## Files Modified/Created

### New Files:
- `scripts/add_project_config_tables.py` - Migration script
- `core/templates/core/project_configure.html` - Configuration UI

### Modified Files:
- `core/views_projects.py` - Added project_configure() view
- `core/urls.py` - Added project_configure route

## Features Matching Jira Images:

✅ **Image 1 (Handwritten Logic)**: Organization-level configuration with work types
✅ **Image 2 (Jira - Better Together)**: Multi-page setup flow  
✅ **Image 3 (Work Types)**: Checkbox selection for Task, Bug, Story, etc.
✅ **Image 4 (Status Tracking)**: Customizable To Do, In Progress, In Review, Done

## Future Enhancements
- Edit project configuration after creation
- Per-project custom fields
- Visual workflow builder
- Work type icons customization
- Status color customization
