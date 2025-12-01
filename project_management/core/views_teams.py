# views.py
import json
import secrets
import string
from django.shortcuts import render
from django.http import JsonResponse, HttpResponseBadRequest

from django.views.decorators.http import require_http_methods
from django.db import connection
from django.contrib.auth.hashers import make_password
from django.views.decorators.csrf import csrf_exempt
from .db_helpers import get_tenant_conn

# ---------- helpers ----------


def json_row(cursor):
    "Convert cursor.fetchone() row to dict if using DictCursor, else fallback"
    cols = [c[0] for c in cursor.description]
    row = cursor.fetchone()
    if not row:
        return None
    return dict(zip(cols, row))

def fetchall_dicts(cursor):
    """
    Return list of dict rows in a DB-backend-agnostic way.
    Works if cursor.fetchall() returns tuples (use cursor.description) or dicts (like pymysql.DictCursor).
    """
    rows = cursor.fetchall()
    if not rows:
        return []
    # if rows are dict-like already (e.g., pymysql DictCursor), return them
    if isinstance(rows[0], dict):
        return rows
    # otherwise, rows are sequences — build dicts using cursor.description
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, r)) for r in rows]


def random_password(n=12):
    alphabet = string.ascii_letters + string.digits + "-_!@#"
    return ''.join(secrets.choice(alphabet) for _ in range(n))

def require_admin(request):
    # simple example: check session role; adapt to your app's auth
    role = request.session.get('role', '').lower()
    user_id = request.session.get('user_id')
    if not user_id or 'admin' not in role:
        return False
    return True

# ---------- Page renders ----------
def people_page(request):
    # renders the people management UI
    return render(request, 'core/people.html', {})

def teams_page(request):
    return render(request, 'core/teams.html', {})

# ---------- People APIs ----------
@require_http_methods(["GET"])
def api_people_list(request):
    conn = get_tenant_conn(request)
    with conn.cursor() as cur:
        cur.execute("SELECT id, email, first_name, last_name, phone, created_at FROM members ORDER BY created_at DESC")
        rows = fetchall_dicts(cur)
    return JsonResponse({'ok': True, 'members': rows})

@csrf_exempt
@require_http_methods(["POST"])
def api_create_member(request):
    # create or update member; optionally create users entry too
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("invalid-json")

    email = data.get('email', '').strip().lower()
    first = data.get('first_name', '').strip()
    last = data.get('last_name', '').strip()
    phone = data.get('phone')
    create_user = data.get('create_user', True)
    team_id = data.get('team_id')
    team_role = data.get('team_role', 'Member')

    if not email:
        return JsonResponse({'ok': False, 'error': 'email required'}, status=400)

    try:
        conn = get_tenant_conn(request)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': 'tenant-resolve-failed', 'detail': str(e)}, status=500)

    member_id = None
    user_id = None
    generated_password = None

    try:
        with conn.cursor() as cur:
            # 1) upsert member
            cur.execute("""
                INSERT INTO members (email, first_name, last_name, phone, created_by)
                VALUES (%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE first_name=VALUES(first_name), last_name=VALUES(last_name), phone=VALUES(phone)
            """, [email, first, last, phone, request.session.get('user_id')])

            # fetch member id (DictCursor => dict)
            cur.execute("SELECT id FROM members WHERE email=%s", [email])
            member_row = cur.fetchone()
            if member_row:
                # use dict access
                member_id = member_row.get('id')
            else:
                member_id = None

            # create user in users table if requested
            if create_user:
                full_name = (first + ' ' + last).strip() or email.split('@')[0]
                generated_password = random_password(10)
                pw_hash = make_password(generated_password)   # use your hashing function if different

                # NOTE: adjust column name 'password_hash' if your users table uses 'password' or 'passwd'
                cur.execute("""
                    INSERT INTO users (email, full_name, password_hash)
                    VALUES (%s,%s,%s)
                    ON DUPLICATE KEY UPDATE full_name=VALUES(full_name), password_hash=VALUES(password_hash)
                """, [email, full_name, pw_hash])

                cur.execute("SELECT id FROM users WHERE email=%s", [email])
                user_row = cur.fetchone()
                if user_row:
                    user_id = user_row.get('id')
                else:
                    user_id = None

            # 3) optionally add to team - idempotent
            if team_id and member_id:
                cur.execute("""
                    INSERT INTO team_memberships (team_id, member_id, team_role, added_by)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE team_role=VALUES(team_role), added_at=CURRENT_TIMESTAMP
                """, [team_id, member_id, team_role, request.session.get('user_id')])

    except Exception as ex:
        # log exception server-side and return friendly message
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Error in api_create_member")
        return JsonResponse({'ok': False, 'error': 'server_error', 'detail': str(ex)}, status=500)

    # return generated password only when a user was created; in prod prefer invite link instead
    return JsonResponse({'ok': True, 'member_id': member_id, 'user_id': user_id, 'password': generated_password})


@require_http_methods(["GET"])
def api_teams_list(request):
    """
    Returns a list of teams with lead email and member count for the current tenant.
    """
    try:
        conn = get_tenant_conn(request)
    except Exception as e:
        return JsonResponse(
            {'ok': False, 'error': 'tenant-resolve-failed', 'detail': str(e)},
            status=500
        )

    try:
        with conn.cursor() as cur:
            # get team + lead email + member_count
            cur.execute("""
                SELECT t.id,
                       t.name,
                       t.description,
                       t.team_lead_id,
                       m.email AS lead_email,
                       (
                           SELECT COUNT(*)
                           FROM team_memberships tm
                           WHERE tm.team_id = t.id
                       ) AS member_count
                FROM teams t
                LEFT JOIN members m ON m.id = t.team_lead_id
                ORDER BY t.name;
            """)
            rows = cur.fetchall()  # DictCursor already returns list[dict]
    except Exception as e:
        import logging
        logging.exception("Error in api_teams_list")
        return JsonResponse(
            {'ok': False, 'error': 'db-query-failed', 'detail': str(e)},
            status=500
        )

    # Convert any datetime fields to ISO strings (JsonResponse-safe)
    for r in rows:
        for k, v in r.items():
            if hasattr(v, 'isoformat'):
                r[k] = v.isoformat()

    return JsonResponse({'ok': True, 'teams': rows})


from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest
import json
import logging
from core.db_helpers import get_tenant_conn  # make sure the path is correct

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def api_create_team(request):
    """
    Create a new team in the current tenant DB.
    Uses get_tenant_conn(request) to obtain tenant connection.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("invalid-json")

    name = (data.get('name') or '').strip()
    desc = data.get('description', '') or ''
    team_lead_id = data.get('team_lead_id')  # optional
    if not name:
        return JsonResponse({'ok': False, 'error': 'name required'}, status=400)

    slug = name.lower().replace(' ', '-')

    try:
        conn = get_tenant_conn(request)
    except Exception as e:
        logger.exception("Tenant resolve failed in api_create_team")
        return JsonResponse({'ok': False, 'error': 'tenant-resolve-failed', 'detail': str(e)}, status=500)

    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO teams (name, slug, description, created_by, team_lead_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (name, slug, desc, request.session.get('user_id'), team_lead_id))

            # Use lastrowid to get the inserted id
            team_id = getattr(cur, 'lastrowid', None)
            # fallback: SELECT LAST_INSERT_ID()
            if not team_id:
                cur.execute("SELECT LAST_INSERT_ID() AS id")
                row = cur.fetchone()
                team_id = row.get('id') if row else None

    except Exception as ex:
        logger.exception("DB error in api_create_team")
        return JsonResponse({'ok': False, 'error': 'db_error', 'detail': str(ex)}, status=500)

    return JsonResponse({'ok': True, 'team_id': team_id})


@require_http_methods(["GET"])
def api_team_members(request, team_id):
    """
    Return team info and its members for the current tenant.
    Uses get_tenant_conn(request) to obtain tenant connection.
    """
    try:
        conn = get_tenant_conn(request)
    except Exception as e:
        logger.exception("Tenant resolve failed in api_team_members")
        return JsonResponse({'ok': False, 'error': 'tenant-resolve-failed', 'detail': str(e)}, status=500)

    try:
        with conn.cursor() as cur:
            # fetch team row (DictCursor => dict)
            cur.execute("SELECT id, name, description, team_lead_id FROM teams WHERE id=%s", (team_id,))
            team_row = cur.fetchone()
            if not team_row:
                return JsonResponse({'ok': False, 'error': 'team not found'}, status=404)

            # fetch members
            cur.execute("""
                SELECT mem.id as member_id,
                       mem.email,
                       mem.first_name,
                       mem.last_name,
                       tm.team_role,
                       tm.added_at
                FROM team_memberships tm
                JOIN members mem ON mem.id = tm.member_id
                WHERE tm.team_id = %s
                ORDER BY tm.added_at DESC
            """, (team_id,))
            members = cur.fetchall() or []

    except Exception as ex:
        logger.exception("DB error in api_team_members")
        return JsonResponse({'ok': False, 'error': 'db_error', 'detail': str(ex)}, status=500)

    # Ensure datetimes are JSON serializable (convert any added_at)
    for m in members:
        for k, v in list(m.items()):
            if hasattr(v, 'isoformat'):
                m[k] = v.isoformat()

    # team_row is already a dict; sanitize any datetimes there as well
    for k, v in list(team_row.items()):
        if hasattr(v, 'isoformat'):
            team_row[k] = v.isoformat()

    return JsonResponse({'ok': True, 'team': team_row, 'members': members})


@csrf_exempt
@require_http_methods(["POST"])
def api_team_add_member(request, team_id):
    """Add or update a member in a team (idempotent)."""

    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("invalid-json")

    member_id = data.get('member_id')
    team_role = data.get('team_role', 'Member')
    if not member_id:
        return JsonResponse({'ok': False, 'error': 'member_id required'}, status=400)

    try:
        conn = get_tenant_conn(request)
    except Exception as e:
        logger.exception("Tenant resolve failed in api_team_add_member")
        return JsonResponse({'ok': False, 'error': 'tenant-resolve-failed', 'detail': str(e)}, status=500)

    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO team_memberships (team_id, member_id, team_role, added_by)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE team_role=VALUES(team_role), added_at=CURRENT_TIMESTAMP
            """, (team_id, member_id, team_role, request.session.get('user_id')))
    except Exception as ex:
        logger.exception("DB error in api_team_add_member")
        return JsonResponse({'ok': False, 'error': 'db_error', 'detail': str(ex)}, status=500)

    return JsonResponse({'ok': True})


@csrf_exempt
@require_http_methods(["POST"])
def api_team_remove_member(request, team_id):
    """Remove a member from a team."""

    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("invalid-json")

    member_id = data.get('member_id')
    if not member_id:
        return JsonResponse({'ok': False, 'error': 'member_id required'}, status=400)

    try:
        conn = get_tenant_conn(request)
    except Exception as e:
        logger.exception("Tenant resolve failed in api_team_remove_member")
        return JsonResponse({'ok': False, 'error': 'tenant-resolve-failed', 'detail': str(e)}, status=500)

    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM team_memberships WHERE team_id=%s AND member_id=%s", (team_id, member_id))
    except Exception as ex:
        logger.exception("DB error in api_team_remove_member")
        return JsonResponse({'ok': False, 'error': 'db_error', 'detail': str(ex)}, status=500)

    return JsonResponse({'ok': True})


@csrf_exempt
@require_http_methods(["POST"])
def api_team_set_lead(request, team_id):
    """Set a team lead (updates team_lead_id and ensures membership)."""

    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("invalid-json")

    member_id = data.get('member_id')
    if not member_id:
        return JsonResponse({'ok': False, 'error': 'member_id required'}, status=400)

    try:
        conn = get_tenant_conn(request)
    except Exception as e:
        logger.exception("Tenant resolve failed in api_team_set_lead")
        return JsonResponse({'ok': False, 'error': 'tenant-resolve-failed', 'detail': str(e)}, status=500)

    try:
        with conn.cursor() as cur:
            # ensure member exists in team as Lead
            cur.execute("""
                INSERT INTO team_memberships (team_id, member_id, team_role, added_by)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE team_role = VALUES(team_role)
            """, (team_id, member_id, 'Lead', request.session.get('user_id')))

            # update the team's lead reference
            cur.execute("UPDATE teams SET team_lead_id=%s WHERE id=%s", (member_id, team_id))
    except Exception as ex:
        logger.exception("DB error in api_team_set_lead")
        return JsonResponse({'ok': False, 'error': 'db_error', 'detail': str(ex)}, status=500)

    return JsonResponse({'ok': True})

