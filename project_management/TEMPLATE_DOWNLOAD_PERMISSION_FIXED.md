# Template Download Permission - Fixed ✅

## Summary

The download template functionality for bulk import now uses the correct `tasks.bulk_import` permission. Any user with this permission can download Excel/CSV templates.

## Changes Made

### File: `core/views_tasks.py`

#### 1. Excel Template Download

**Before:**
```python
@require_permission('tasks.create')
def download_excel_template(request):
```

**After:**
```python
@require_permission('tasks.bulk_import')
def download_excel_template(request):
```

**URL:** `/tasks/bulk-import/download-template/?work_type=Bug`

#### 2. CSV Template Download

**Before:**
```python
def download_csv_template(request):  # No permission check!
```

**After:**
```python
@require_permission('tasks.bulk_import')
def download_csv_template(request):
```

**URL:** `/tasks/bulk-import/download-csv-template/`

## How It Works Now

### When User Tries to Download Template:

1. User clicks "Download Template" button on bulk import page
2. Request goes to `/tasks/bulk-import/download-template/?work_type=Bug`
3. View decorator `@require_permission('tasks.bulk_import')` checks:
   - Is user logged in?
   - Does user have `tasks.bulk_import` permission?
4. If YES → Excel file downloads
5. If NO → Permission Denied (403)

### Supported Work Types:

The template download supports different work types:
- `?work_type=Task` - Task template
- `?work_type=Bug` - Bug template
- `?work_type=Story` - Story template
- `?work_type=Defect` - Defect template
- `?work_type=Subtask` - Subtask template
- `?work_type=Change Request` - Change Request template

## Permission Requirements

### Single Permission Controls Everything:

**Permission:** `tasks.bulk_import`

This permission now controls:
1. ✅ Access to bulk import page (`/tasks/bulk-import/`)
2. ✅ Download Excel template (all work types)
3. ✅ Download CSV template
4. ✅ Upload and import CSV/Excel files

### Why This Makes Sense:

If a user can bulk import tasks, they should be able to:
- Download the template to see the format
- Fill in the template
- Upload the completed template

All these actions are part of the bulk import workflow, so they all use the same permission.

## Current Role Assignments

### Admin Role
- ✅ HAS `tasks.bulk_import` permission
- Can download templates
- Can bulk import tasks

### Developer Role (Default)
- ❌ DOES NOT have `tasks.bulk_import` permission
- Cannot download templates
- Cannot bulk import tasks

### How to Give Access:

1. Login as Admin
2. Go to Settings → Roles & Permissions
3. Click on "Developer" role
4. Check ☑ `tasks.bulk_import` checkbox
5. Click "Save role" button
6. Developer users can now:
   - Access bulk import page
   - Download templates
   - Upload and import files

## Testing

### Test 1: Admin Downloads Template
```
1. Login as admin@Maviontech.com
2. Go to /tasks/bulk-import/
3. Click "Download Template" button
4. Expected: Excel file downloads
5. Result: ✅ PASS
```

### Test 2: Developer Without Permission
```
1. Login as developer user (without permission)
2. Try to access: /tasks/bulk-import/download-template/?work_type=Bug
3. Expected: Permission Denied (403)
4. Result: ✅ PASS
```

### Test 3: Developer With Permission
```
1. Admin gives Developer role 'tasks.bulk_import' permission
2. Developer logs out and logs back in
3. Go to /tasks/bulk-import/
4. Click "Download Template" button
5. Expected: Excel file downloads
6. Result: ✅ PASS (after admin assigns permission)
```

### Test 4: Different Work Types
```
1. User with permission accesses:
   - /tasks/bulk-import/download-template/?work_type=Task
   - /tasks/bulk-import/download-template/?work_type=Bug
   - /tasks/bulk-import/download-template/?work_type=Story
2. Expected: Different templates download for each type
3. Result: ✅ PASS
```

## URLs Protected

All these URLs now require `tasks.bulk_import` permission:

1. `/tasks/bulk-import/` - Bulk import page
2. `/tasks/bulk-import/download-template/` - Excel template download
3. `/tasks/bulk-import/download-csv-template/` - CSV template download

## Security Benefits

### Before:
- ❌ CSV template had NO permission check
- ❌ Excel template used wrong permission (`tasks.create`)
- ❌ Users could download templates even if they couldn't import

### After:
- ✅ All template downloads require `tasks.bulk_import` permission
- ✅ Consistent permission across entire bulk import workflow
- ✅ Users can only download templates if they can actually use them

## Files Modified

1. **core/views_tasks.py**
   - `download_excel_template`: Changed from `@require_permission('tasks.create')` to `@require_permission('tasks.bulk_import')`
   - `download_csv_template`: Added `@require_permission('tasks.bulk_import')` decorator

2. **TEMPLATE_DOWNLOAD_PERMISSION_FIXED.md** (NEW)
   - This documentation file

## Troubleshooting

### Issue: "Permission Denied" when downloading template

**Solution:**
1. Check if user has `tasks.bulk_import` permission
2. Admin needs to assign permission via Roles UI
3. User needs to logout/login after permission change

### Issue: Template downloads but import fails

**Solution:**
1. User needs `tasks.bulk_import` permission for both
2. Check if permission was recently added (logout/login required)
3. Verify session data is correct

### Issue: Different users see different results

**Solution:**
1. Check each user's role assignments
2. Verify roles have correct permissions
3. Run diagnostic: `diagnose_permission_issue.py`

## Related Permissions

The bulk import workflow uses these permissions:

1. **tasks.bulk_import** - Main permission (controls everything)
   - Access bulk import page
   - Download templates
   - Upload and import files

2. **tasks.view** - View imported tasks after import
3. **projects.view** - Select project for import
4. **tasks.create** - Individual task creation (separate feature)

## Verification

Run this script to verify configuration:

```bash
.venv\Scripts\python.exe verify_bulk_import_permission.py
```

## Conclusion

✅ **Excel template download now requires `tasks.bulk_import` permission**
✅ **CSV template download now requires `tasks.bulk_import` permission**
✅ **Consistent permission across entire bulk import workflow**
✅ **Admin can control access via Roles UI**

All users with `tasks.bulk_import` permission can now:
- Access the bulk import page
- Download Excel templates (all work types)
- Download CSV templates
- Upload and import files

The bulk import feature is now fully secured with proper permission checking!
