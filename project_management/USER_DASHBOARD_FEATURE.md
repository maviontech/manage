# User Dashboard Feature Documentation

## Overview
This feature allows users to toggle between two dashboard views:
1. **Admin Dashboard** - Shows all team tasks and projects (original view)
2. **My Personal Dashboard** - Shows only the logged-in user's assigned tasks and projects

## What Was Added

### 1. New View Function (`core/views.py`)
- **Function:** `user_dashboard_view(request)`
- **Purpose:** Displays dashboard data filtered to show only the logged-in user's tasks and projects
- **Key Differences from Admin Dashboard:**
  - Tasks: Only shows tasks assigned to the current user (not using `visible_user_ids`)
  - Projects: Only shows projects where user is owner or member
  - Statistics: All metrics calculated based on user's own data

### 2. New URL Route (`core/urls.py`)
- **Route:** `/user-dashboard/`
- **Name:** `user_dashboard`
- **Maps to:** `views.user_dashboard_view`

### 3. Dashboard Toggle Button (`core/templates/core/base.html`)
- **Location:** Header, near notifications (top-right area)
- **Button ID:** `dashboard-toggle`
- **Behavior:**
  - Only visible on dashboard pages (`/dashboard/` or `/user-dashboard/`)
  - Label changes based on current view:
    - On Admin Dashboard: Shows "My View" button
    - On User Dashboard: Shows "Admin View" button
  - Clicking toggles between the two views

### 4. Visual Indicators (`core/templates/core/dashboard.html`)
- **Banner at top of dashboard:**
  - **Blue banner** for "My Personal Dashboard" (user view)
  - **Green banner** for "Admin Dashboard" (admin/team view)
- **Banner includes:**
  - Icon representing the view type
  - Title and description
  - Quick switch button to alternate view

## How It Works

### User Flow:
1. User logs in and lands on the default dashboard (`/dashboard/`)
2. A **green banner** appears showing "Admin Dashboard" with team data
3. User sees a **toggle button** in the header (next to notifications)
4. User clicks "My View" button
5. Dashboard switches to `/user-dashboard/` with a **blue banner**
6. Now showing only their personal tasks, projects, and statistics
7. User can click "Admin View" to go back to team view

### Data Filtering Logic:

**Admin Dashboard (`/dashboard/`):**
```python
# Uses visible_user_ids (includes subordinates if team lead)
visible_user_ids = get_visible_task_user_ids(conn, member_id)
# Shows tasks assigned to any visible user
```

**User Dashboard (`/user-dashboard/`):**
```python
# Only uses member_id (current user)
assigned_count = "SELECT COUNT(*) FROM tasks WHERE assigned_to=%s"
# Shows only tasks assigned to current user
```

## Key Metrics Shown

Both dashboards show the same layout with these metrics:
- Total Tasks Assigned
- Active Projects
- Tasks Completed
- Tasks Pending
- Task Breakdown (Donut Chart)
- Priority Distribution
- Recent Activity
- Planned Tasks (next 7 days)
- Line chart (tasks created/completed over last 7 days)

The **only difference** is the data source - admin view shows team data, user view shows personal data.

## Button Styling

The toggle button in the header:
- Uses same styling as notifications button (`.btn-ghost`)
- Icon: Grid/dashboard icon (4 squares)
- Text label: "My View" or "Admin View"
- Auto-hides on non-dashboard pages

## Testing Checklist

✅ Test as regular user:
   - Should see toggle button on dashboard
   - Should see their own tasks and projects in "My View"
   - Should see team data in "Admin View"

✅ Test as team lead:
   - "Admin View" should show subordinate tasks
   - "My View" should show only their own tasks

✅ Test navigation:
   - Toggle button should work smoothly
   - Banners should display correctly
   - Data should be accurate for each view

✅ Test on different screen sizes:
   - Button should be visible on mobile
   - Banners should be responsive

## Files Modified

1. `core/views.py` - Added `user_dashboard_view()` function
2. `core/urls.py` - Added `/user-dashboard/` route
3. `core/templates/core/base.html` - Added toggle button and JavaScript
4. `core/templates/core/dashboard.html` - Added view indicator banners

## Future Enhancements (Optional)

- Add user preferences to remember last selected view
- Add more personalized widgets in user view (e.g., "My Goals", "My Performance")
- Add export functionality specific to user view
- Add notifications when switching views
- Add keyboard shortcut (e.g., Ctrl+Shift+D) to toggle views

## Technical Notes

- Both views use the same template (`dashboard.html`)
- Context variable `is_user_dashboard` differentiates the views
- Button visibility controlled via JavaScript in `DOMContentLoaded` event
- No database schema changes required
- Compatible with existing authentication and tenant system
