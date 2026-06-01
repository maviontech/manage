"""
Work Week View - Display tasks organized by day of the week
"""
import datetime
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from .db_helpers import get_tenant_conn, get_visible_task_user_ids

def work_week_view(request):
    """
    Display tasks organized by day of the week (Monday to Sunday)
    Shows current week with ability to navigate to previous/next weeks
    """
    # Check authentication
    member_id = request.session.get('member_id') or request.session.get('user_id')
    if not member_id:
        return redirect('login_password')
    
    conn = get_tenant_conn(request)
    cur = conn.cursor()
    
    # Get current user ID
    user_id = request.session.get("user_id")
    if not user_id:
        user_id = request.session.get("member_id")
    
    # Get week offset from query parameter (0 = current week, -1 = last week, 1 = next week)
    week_offset = int(request.GET.get('week', 0))
    
    # Calculate the start of the week (Monday)
    today = datetime.date.today()
    days_since_monday = today.weekday()  # Monday = 0, Sunday = 6
    week_start = today - datetime.timedelta(days=days_since_monday) + datetime.timedelta(weeks=week_offset)
    week_end = week_start + datetime.timedelta(days=6)
    
    # Generate all 7 days of the week
    week_days = []
    for i in range(7):
        day = week_start + datetime.timedelta(days=i)
        week_days.append({
            'date': day,
            'day_name': day.strftime('%A'),
            'day_short': day.strftime('%a'),
            'day_number': day.day,
            'month': day.strftime('%b'),
            'is_today': day == today,
            'is_weekend': day.weekday() >= 5,  # Saturday = 5, Sunday = 6
            'tasks': []
        })
    
    # Get visible task user IDs based on visibility rules
    visible_user_ids = get_visible_task_user_ids(conn, user_id) if user_id else []
    
    if visible_user_ids:
        placeholders = ','.join(['%s'] * len(visible_user_ids))
        
        # Get all tasks for the week
        cur.execute(f"""
            SELECT 
                t.id,
                t.title,
                t.description,
                t.status,
                t.priority,
                t.work_type,
                t.due_date,
                t.created_at,
                t.assigned_to,
                t.assigned_type,
                p.name AS project_name,
                CONCAT(m.first_name, ' ', m.last_name) AS assigned_name,
                tm.name AS team_name
            FROM tasks t
            LEFT JOIN projects p ON t.project_id = p.id
            LEFT JOIN members m ON t.assigned_type = 'member' AND t.assigned_to = m.id
            LEFT JOIN teams tm ON t.assigned_type = 'team' AND t.assigned_to = tm.id
            WHERE t.assigned_type = 'member' 
                AND t.assigned_to IN ({placeholders})
                AND DATE(t.due_date) >= %s 
                AND DATE(t.due_date) <= %s
                AND t.status != 'Closed'
            ORDER BY t.due_date, t.priority DESC, t.created_at
        """, tuple(visible_user_ids) + (week_start, week_end))
        
        tasks = cur.fetchall()
        
        # Organize tasks by day
        for task in tasks:
            task_due_date = task['due_date']
            if task_due_date:
                # Normalize datetime -> date so comparisons work even when due_date is DATETIME
                try:
                    if isinstance(task_due_date, datetime.datetime):
                        task_due_date = task_due_date.date()
                except Exception:
                    pass

                # Find the matching day
                for day in week_days:
                    if day['date'] == task_due_date:
                        day['tasks'].append({
                            'id': task['id'],
                            'title': task['title'],
                            'description': task['description'],
                            'status': task['status'],
                            'priority': task['priority'],
                            'work_type': task['work_type'] or 'Task',
                            'project_name': task['project_name'],
                            'assigned_name': task['assigned_name'] or task['team_name']
                        })
                        break
    
    # Get task counts by status for the week
    task_counts = {
        'total': 0,
        'open': 0,
        'in_progress': 0,
        'review': 0,
        'blocked': 0
    }
    
    if visible_user_ids:
        cur.execute(f"""
            SELECT 
                status,
                COUNT(*) as count
            FROM tasks
            WHERE assigned_type = 'member' 
                AND assigned_to IN ({placeholders})
                AND DATE(due_date) >= %s 
                AND DATE(due_date) <= %s
                AND status != 'Closed'
            GROUP BY status
        """, tuple(visible_user_ids) + (week_start, week_end))
        
        status_counts = cur.fetchall()
        
        for row in status_counts:
            status = row['status'].lower().replace(' ', '_')
            count = row['count']
            task_counts['total'] += count
            
            if status in ['open', 'new']:
                task_counts['open'] += count
            elif status in ['in_progress', 'in-progress']:
                task_counts['in_progress'] += count
            elif status == 'review':
                task_counts['review'] += count
            elif status == 'blocked':
                task_counts['blocked'] += count
    
    cur.close()
    
    # Format week range for display
    week_range = f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}"
    
    return render(
        request,
        'core/work_week.html',
        {
            'week_days': week_days,
            'week_start': week_start,
            'week_end': week_end,
            'week_range': week_range,
            'week_offset': week_offset,
            'task_counts': task_counts,
            'today': today,
            'page': 'work_week'
        }
    )


@require_GET
def api_work_week_tasks(request):
    """
    API endpoint to get tasks for a specific date
    """
    # Check authentication
    member_id = request.session.get('member_id') or request.session.get('user_id')
    if not member_id:
        return JsonResponse({'success': False, 'error': 'Authentication required'}, status=401)
    
    try:
        date_str = request.GET.get('date')
        if not date_str:
            return JsonResponse({'success': False, 'error': 'Date parameter required'})
        
        target_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        
        conn = get_tenant_conn(request)
        cur = conn.cursor()
        
        user_id = request.session.get("user_id")
        visible_user_ids = get_visible_task_user_ids(conn, user_id) if user_id else []
        
        if not visible_user_ids:
            return JsonResponse({'success': True, 'tasks': []})
        
        placeholders = ','.join(['%s'] * len(visible_user_ids))
        
        cur.execute(f"""
            SELECT 
                t.id,
                t.title,
                t.description,
                t.status,
                t.priority,
                t.work_type,
                p.name AS project_name
            FROM tasks t
            LEFT JOIN projects p ON t.project_id = p.id
            WHERE t.assigned_type = 'member' 
                AND t.assigned_to IN ({placeholders})
                AND DATE(t.due_date) = %s
                AND t.status != 'Closed'
            ORDER BY t.priority DESC, t.created_at
        """, tuple(visible_user_ids) + (target_date,))
        
        tasks = cur.fetchall()
        cur.close()
        
        return JsonResponse({
            'success': True,
            'tasks': list(tasks)
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
