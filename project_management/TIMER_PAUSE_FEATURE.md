# Timer Pause Feature - Implementation Guide

## Overview
Added pause and resume functionality to the time tracker, allowing users to temporarily pause their active timer and resume it later.

## Changes Made

### 1. Database Schema Update
**File:** `scripts/add_timer_pause_columns.py`

Added three new columns to the `timer_sessions` table:
- `paused` (TINYINT): Flag indicating if timer is currently paused (0 or 1)
- `paused_at` (DATETIME): Timestamp when timer was paused
- `paused_duration` (INT): Total duration (in milliseconds) the timer has been paused

**To apply the migration:**
```bash
python scripts/add_timer_pause_columns.py
```

This script will:
- Connect to the master database
- Update all active tenant databases
- Add the pause columns to existing `timer_sessions` tables
- Skip databases that don't have timer tables or already have the columns

### 2. Backend API Endpoints
**File:** `core/views.py`

#### New Endpoints:

**POST `/api/timer/pause`**
- Pauses the current running timer
- Records the pause timestamp
- Returns: `{ success: true, session_id: int, paused_at: datetime }`

**POST `/api/timer/resume`**
- Resumes a paused timer
- Calculates and accumulates pause duration
- Returns: `{ success: true, session_id: int, resumed_at: datetime, paused_duration: int }`

#### Updated Endpoint:

**GET `/api/timer/current`**
- Now includes pause state information:
  - `paused`: Boolean indicating if timer is paused
  - `paused_at`: Timestamp when paused (if currently paused)
  - `paused_duration`: Total accumulated pause time in milliseconds

### 3. URL Routes
**File:** `core/urls.py`

Added two new URL patterns:
```python
path('api/timer/pause', views.api_timer_pause, name='api_timer_pause'),
path('api/timer/resume', views.api_timer_resume, name='api_timer_resume'),
```

### 4. Frontend Updates
**File:** `core/templates/core/timer.html`

- Fixed pause button visibility (uncommented line 861)
- Pause button now properly hides when timer is paused
- Resume and "Switch Task" buttons appear when timer is paused
- Stop button hides when timer is paused

## Usage Instructions

### For Users:

1. **Start a timer**: Click "Start Timer" and optionally select a task
2. **Pause the timer**: Click "Pause Timer" button to take a break
3. **Resume the timer**: Click "Resume Timer" to continue tracking time
4. **Switch tasks**: While paused, click "Start Timer for Another Task" to work on something else
5. **Complete timer**: Click "Complete Timer" to finish and save the session

### How It Works:

- When you pause a timer, the current time is recorded
- When you resume, the system calculates how long it was paused
- The pause duration is tracked separately and excluded from the total work time
- You can pause and resume multiple times - all pause durations are accumulated
- When you stop the timer, the final duration excludes all pause time

### Example:
```
Start:  10:00 AM
Pause:  10:30 AM (worked 30 minutes)
Resume: 11:00 AM (paused 30 minutes)
Pause:  11:15 AM (worked 15 more minutes)
Resume: 11:30 AM (paused 15 minutes)
Stop:   11:45 AM (worked 15 more minutes)

Total work time: 30 + 15 + 15 = 60 minutes
Total pause time: 30 + 15 = 45 minutes
```

## Technical Details

### Pause Duration Calculation:
- Stored in milliseconds for precision
- Calculated on resume: `pause_duration_ms = (now - paused_at) * 1000`
- Accumulated across multiple pause/resume cycles
- Frontend uses this to calculate accurate elapsed work time

### State Management:
```javascript
// Frontend tracks:
- paused: boolean (is timer currently paused)
- pausedAt: timestamp (when it was paused)
- pausedDuration: milliseconds (accumulated pause time)

// When calculating displayed time:
if (paused) {
    elapsed = (pausedAt - startTime - pausedDuration) / 1000
} else {
    elapsed = (now - startTime - pausedDuration) / 1000
}
```

### Database State:
- `is_running = 1`: Timer is active (may be paused or running)
- `paused = 1`: Timer is paused (is_running must also be 1)
- `paused = 0`: Timer is actively running (is_running must also be 1)
- `is_running = 0`: Timer is completed/stopped

## Testing

1. Start a timer
2. Verify the pause button appears
3. Click pause - verify:
   - Pause button disappears
   - Resume and Switch Task buttons appear
   - Timer display stops updating
   - Status badge shows "Timer Idle"
4. Click resume - verify:
   - Pause button reappears
   - Resume/Switch buttons disappear
   - Timer continues from where it left off
   - Status badge shows "Timer Running"
5. Complete the timer and check history shows correct duration

## Troubleshooting

### Pause button not appearing:
- Run the database migration script
- Restart Django server
- Clear browser cache

### Pause duration not being tracked:
- Check database columns exist: `paused`, `paused_at`, `paused_duration`
- Verify API endpoints are registered in urls.py
- Check browser console for JavaScript errors

### Timer showing incorrect time:
- Ensure `pausedDuration` is properly calculated in backend
- Verify frontend `updateTimerDisplay()` uses pausedDuration
- Check timezone settings

## Future Enhancements

Potential improvements:
- Add pause/resume history in session details
- Show pause duration separately in timer history
- Add keyboard shortcuts (Space to pause/resume)
- Notification when timer has been paused for extended time
- Automatic pause detection (idle time)
- Pause reasons/notes

## Files Modified Summary

1. `scripts/add_timer_pause_columns.py` - NEW migration script
2. `core/views.py` - Added pause/resume API endpoints
3. `core/urls.py` - Registered new API routes
4. `core/templates/core/timer.html` - Fixed pause button visibility

## Migration Commands

```bash
# 1. Apply database changes
cd scripts
python add_timer_pause_columns.py

# 2. Restart Django server
python manage.py runserver

# 3. Test the feature in browser
# Navigate to: http://localhost:8000/timer/
```

## Support

If you encounter issues:
1. Check logs in `logs/` directory
2. Verify database schema has new columns
3. Ensure all API endpoints return expected responses
4. Test with browser developer tools console open
