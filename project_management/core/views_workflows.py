# views_workflows.py
from django.shortcuts import render, redirect
from .tenant_context import get_current_tenant
from .db_helpers import get_tenant_conn
import logging

logger = logging.getLogger('project_management')


def workflows_view(request):
    """
    Workflows page - displays workflow management interface
    """
    tenant = get_current_tenant() or request.session.get('tenant_config')
    if not tenant:
        return redirect('identify')

    member_id = request.session.get('member_id')
    if not member_id:
        return redirect('login_password')

    try:
        conn = get_tenant_conn(request)
        cur = conn.cursor()

        # Check if workflows table exists, create if not
        try:
            cur.execute("SHOW TABLES LIKE 'workflows'")
            table_exists = cur.fetchone()
            
            if not table_exists:
                logger.info("Creating workflows table...")
                cur.execute("""
                    CREATE TABLE workflows (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        description TEXT,
                        status ENUM('Active', 'Draft', 'Archived') DEFAULT 'Draft',
                        created_by INT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        INDEX idx_status (status),
                        INDEX idx_created_at (created_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                
                # Add sample data
                sample_workflows = [
                    ('Development Workflow', 'Standard development process from planning to deployment', 'Active'),
                    ('Bug Fix Workflow', 'Quick workflow for addressing and resolving bugs', 'Active'),
                    ('Feature Request Workflow', 'Process for evaluating and implementing new features', 'Draft'),
                    ('Code Review Workflow', 'Peer review process for code quality assurance', 'Active'),
                    ('Release Workflow', 'Steps for preparing and deploying releases', 'Draft'),
                ]
                
                for name, description, status in sample_workflows:
                    cur.execute("""
                        INSERT INTO workflows (name, description, status)
                        VALUES (%s, %s, %s)
                    """, (name, description, status))
                
                conn.commit()
                logger.info("Workflows table created with sample data")
        except Exception as table_error:
            logger.warning(f"Error checking/creating workflows table: {table_error}")

        # Get workflow statistics
        try:
            cur.execute("""
                SELECT 
                    COUNT(*) as total_workflows,
                    SUM(CASE WHEN status = 'Active' THEN 1 ELSE 0 END) as active_workflows,
                    SUM(CASE WHEN status = 'Draft' THEN 1 ELSE 0 END) as draft_workflows,
                    SUM(CASE WHEN status = 'Archived' THEN 1 ELSE 0 END) as archived_workflows
                FROM workflows
            """)
            workflow_stats_row = cur.fetchone()
            
            if workflow_stats_row:
                if isinstance(workflow_stats_row, dict):
                    workflow_stats = workflow_stats_row
                else:
                    workflow_stats = {
                        'total_workflows': workflow_stats_row[0] or 0,
                        'active_workflows': workflow_stats_row[1] or 0,
                        'draft_workflows': workflow_stats_row[2] or 0,
                        'archived_workflows': workflow_stats_row[3] or 0
                    }
            else:
                workflow_stats = {'total_workflows': 0, 'active_workflows': 0, 'draft_workflows': 0, 'archived_workflows': 0}
            
            # Get recent workflows
            cur.execute("""
                SELECT id, name, description, status, created_at, updated_at
                FROM workflows
                ORDER BY updated_at DESC
                LIMIT 10
            """)
            recent_workflows = cur.fetchall()
        except Exception as query_error:
            logger.warning(f"Error querying workflows: {query_error}")
            workflow_stats = {'total_workflows': 0, 'active_workflows': 0, 'draft_workflows': 0, 'archived_workflows': 0}
            recent_workflows = []

        cur.close()
        conn.close()

        context = {
            'workflow_stats': workflow_stats,
            'recent_workflows': recent_workflows if recent_workflows else [],
        }

    except Exception as e:
        logger.error(f"Error loading workflows: {e}")
        context = {
            'workflow_stats': {'total_workflows': 0, 'active_workflows': 0, 'draft_workflows': 0, 'archived_workflows': 0},
            'recent_workflows': [],
        }

    return render(request, 'core/workflows.html', context)


def priorities_view(request):
    """
    Priorities page - displays priority management interface
    """
    tenant = get_current_tenant() or request.session.get('tenant_config')
    if not tenant:
        return redirect('identify')

    member_id = request.session.get('member_id')
    if not member_id:
        return redirect('login_password')

    try:
        conn = get_tenant_conn(request)
        cur = conn.cursor()

        # Get priority statistics
        cur.execute("""
            SELECT 
                priority,
                COUNT(*) as count,
                SUM(CASE WHEN status = 'Closed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status IN ('Open', 'New') THEN 1 ELSE 0 END) as open_tasks,
                SUM(CASE WHEN status = 'In Progress' THEN 1 ELSE 0 END) as in_progress
            FROM active_tasks
            GROUP BY priority
        """)
        priority_stats_raw = cur.fetchall()
        
        # Calculate completion percentages
        priority_stats = []
        for stat in priority_stats_raw:
            if isinstance(stat, dict):
                count = stat.get('count', 0) or 0
                completed = stat.get('completed', 0) or 0
                completion_percent = round((completed / count * 100) if count > 0 else 0, 1)
                priority_stats.append({
                    'priority': stat.get('priority', 'Normal'),
                    'count': count,
                    'completed': completed,
                    'open_tasks': stat.get('open_tasks', 0) or 0,
                    'in_progress': stat.get('in_progress', 0) or 0,
                    'completion_percent': completion_percent
                })
            else:
                count = stat[1] or 0
                completed = stat[2] or 0
                completion_percent = round((completed / count * 100) if count > 0 else 0, 1)
                priority_stats.append({
                    'priority': stat[0] or 'Normal',
                    'count': count,
                    'completed': completed,
                    'open_tasks': stat[3] or 0,
                    'in_progress': stat[4] or 0,
                    'completion_percent': completion_percent
                })

        # Get high priority tasks
        cur.execute("""
            SELECT id, title, priority, status, due_date, assigned_to
            FROM active_tasks
            WHERE priority IN ('Critical', 'High')
            AND status NOT IN ('Closed', 'Completed')
            ORDER BY 
                CASE priority 
                    WHEN 'Critical' THEN 1 
                    WHEN 'High' THEN 2 
                    ELSE 3 
                END,
                due_date ASC
            LIMIT 15
        """)
        high_priority_tasks = cur.fetchall()

        cur.close()
        conn.close()

        context = {
            'priority_stats': priority_stats if priority_stats else [],
            'high_priority_tasks': high_priority_tasks if high_priority_tasks else [],
        }

    except Exception as e:
        logger.error(f"Error loading priorities: {e}")
        context = {
            'priority_stats': [],
            'high_priority_tasks': [],
        }

    return render(request, 'core/priorities.html', context)
