# Bug Fix Summary: Internal Server Error (500) Across Multiple Modules

## Issue Description
When users copied URLs from one browser (Chrome) and pasted them in another browser (Edge) without being logged in, the application displayed a "Server Error (500)" instead of redirecting to the login page.

## Root Cause
Multiple view functions were calling `get_tenant_conn(request)` or `get_tenant_conn_and_cursor(request)` **before** checking if the user was authenticated. When an unauthenticated request tried to access the database:

1. The session was empty (no authentication cookies in the new browser)
2. `get_tenant_conn()` tried to resolve tenant credentials from the session
3. Since the session was empty, it couldn't find the required database credentials
4. This raised a `RuntimeError`, causing the 500 Internal Server Error

## Solution
Added authentication checks **before** calling any database connection functions in all affected views. Unauthenticated users are now properly redirected to the login page instead of encountering a 500 error.

## Files Modified

### 1. core/views_projects.py
**Fixed Functions:**
- `projects_list()` - Added authentication check before database connection
- `projects_search_ajax()` - Returns 401 JSON response for unauthenticated requests
- `subprojects_list()` - Added authentication check before database connection

### 2. core/views_teams.py
**Fixed Functions:**
- `people_page()` - Added authentication check before rendering
- `teams_page()` - Added authentication check before rendering
- `api_people_list()` - Returns 401 JSON response for unauthenticated requests
- `api_create_member()` - Returns 401 JSON response for unauthenticated requests
- `api_teams_list()` - Returns 401 JSON response for unauthenticated requests
- `api_create_team()` - Returns 401 JSON response for unauthenticated requests
- `api_team_members()` - Returns 401 JSON response for unauthenticated requests
- `api_team_add_member()` - Returns 401 JSON response for unauthenticated requests
- `api_team_remove_member()` - Returns 401 JSON response for unauthenticated requests
- `api_team_set_lead()` - Returns 401 JSON response for unauthenticated requests

### 3. core/views_workweek.py
**Fixed Functions:**
- `work_week_view()` - Added authentication check before database connection
- `api_work_week_tasks()` - Returns 401 JSON response for unauthenticated requests

### 4. core/views.py
**Fixed Functions:**
- `api_team_list()` - Returns 401 JSON response for unauthenticated requests
- `api_team_summary()` - Returns 401 JSON response for unauthenticated requests

## Authentication Pattern Used

### For HTML Views:
```python
def view_function(request):
    # Check authentication
    member_id = request.session.get('member_id') or request.session.get('user_id')
    if not member_id:
        return redirect('login_password')
    
    # Now safe to call database connection
    conn = get_tenant_conn(request)
    # ... rest of the code
```

### For API/JSON Views:
```python
def api_function(request):
    # Check authentication
    member_id = request.session.get('member_id') or request.session.get('user_id')
    if not member_id:
        return JsonResponse({'ok': False, 'error': 'Authentication required'}, status=401)
    
    # Now safe to call database connection
    conn = get_tenant_conn(request)
    # ... rest of the code
```

## Affected Modules (Now Fixed)
All the following modules now properly handle unauthenticated access:
- ✅ People
- ✅ Projects  
- ✅ Tasks (already had `@require_permission` decorator)
- ✅ Unassigned (already had `@require_permission` decorator)
- ✅ Bulk Import (already had `@require_permission` decorator)
- ✅ Tasks Board (already had `@require_permission` decorator)
- ✅ Analytics
- ✅ Teams
- ✅ Work Week
- ✅ Change Password (already had authentication check)
- ✅ Settings (already had `@require_permission` decorator)
- ✅ Roles (already had `@require_permission` decorator)

## Testing Recommendations

1. **Cross-Browser URL Test:**
   - Log in to the application in Chrome
   - Navigate to any module (e.g., `/projects/`, `/teams/`, `/work-week/`)
   - Copy the URL
   - Open Edge (or any other browser) without logging in
   - Paste the URL
   - **Expected:** User should be redirected to the login page
   - **Previous Behavior:** Server Error (500)

2. **API Endpoint Test:**
   - Make API requests to endpoints like `/api/teams/`, `/api/people/list/`, etc. without authentication
   - **Expected:** HTTP 401 Unauthorized with JSON error message
   - **Previous Behavior:** Server Error (500)

3. **Normal Flow Test:**
   - Log in normally
   - Navigate through all modules
   - **Expected:** Everything should work as before
   - All module pages should load successfully

## Impact
- **Severity:** Critical (was blocking all module access)
- **Priority:** High
- **User Experience:** Significantly improved - users now see appropriate login page instead of generic error
- **Security:** Improved - proper authentication enforcement across all views
- **Backward Compatibility:** No breaking changes - all existing functionality preserved

## Notes
- The fix follows Django best practices for authentication
- No database schema changes required
- No configuration changes required
- All existing `@require_permission` decorators remain in place (they already handled authentication)
- The fix is defensive - checks authentication at the earliest possible point
