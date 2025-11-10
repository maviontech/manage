
# views/admin_tenants.py  (or wherever your view lives)
import secrets
import string
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
import os
from django.views.decorators.csrf import csrf_exempt

import pymysql
from .db_initializer import DBInitializer  # uses the file you already have. :contentReference[oaicite:1]{index=1}
from .auth import hash_password  # same helper used in db_initializer

MASTER_DB = os.environ.get('MASTER_DB_NAME', 'master_db')
# Ensure ADMIN_CONF exists (same as elsewhere in your project)

ADMIN_CONF = {
    'host': getattr(settings, 'MYSQL_ADMIN_HOST', '127.0.0.1'),
    'port': int(getattr(settings, 'MYSQL_ADMIN_PORT', 3306)),
    'user': getattr(settings, 'MYSQL_ADMIN_USER', 'root'),
    'password': getattr(settings, 'MYSQL_ADMIN_PWD', 'root'),
    'cursorclass': pymysql.cursors.DictCursor,
    'autocommit': True
}

def _rand_password(length=12):
    alphabet = string.ascii_letters + string.digits + "-_!@#"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

@csrf_exempt
def new_tenant_view(request):
    """
    Create a new tenant, provision DB & user, run tenant DDL (full set in db_initializer.py),
    seed roles & permissions and create an initial admin user + tenant_role_assignment.

    Ensures master_db and clients_master exist (creates them if missing) before writing.
    """
    if request.method == 'GET':
        return render(request, 'core/new_tenant.html')

    client_name = request.POST.get('client_name', '').strip()
    domain = request.POST.get('domain', '').strip()
    db_name = request.POST.get('db_name', '').strip()
    if not client_name or not domain or not db_name:
        messages.error(request, "All fields are required.")
        return redirect('new_tenant')

    tenant_domain_postfix = '@' + domain

    # Ensure master_db and clients_master exist
    try:
        admin_conn = pymysql.connect(
            host=ADMIN_CONF['host'],
            port=ADMIN_CONF['port'],
            user=ADMIN_CONF['user'],
            password=ADMIN_CONF['password'],
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )
        admin_cur = admin_conn.cursor()

        # 1. Create master_db if missing
        admin_cur.execute("CREATE DATABASE IF NOT EXISTS master_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")

        # 2. Create clients_master table safely
        admin_cur.execute("""
            CREATE TABLE IF NOT EXISTS master_db.clients_master (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                client_name VARCHAR(255) NOT NULL,
                domain_postfix VARCHAR(255) NOT NULL,
                db_name VARCHAR(255) NOT NULL,
                db_host VARCHAR(100) DEFAULT '127.0.0.1',
                db_engine VARCHAR(50) DEFAULT 'mysql',
                db_user VARCHAR(255),
                db_password VARCHAR(255),
                created_at DATETIME,
                updated_at DATETIME,
                UNIQUE KEY ux_clients_master_dbname (db_name),
                UNIQUE KEY ux_clients_master_domain (domain_postfix),
                INDEX idx_clients_master_db_domain (db_name, domain_postfix)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # Check for duplicate tenants
        admin_cur.execute("""
            SELECT COUNT(*) AS c
            FROM master_db.clients_master
            WHERE db_name=%s OR domain_postfix=%s
        """, (db_name, tenant_domain_postfix))
        row = admin_cur.fetchone()
        if row and row.get('c', 0) > 0:
            messages.error(request, "Tenant DB name or domain already exists. Choose a different db_name/domain.")
            admin_cur.close()
            admin_conn.close()
            return redirect('new_tenant')

        # Insert into clients_master
        admin_cur.execute("""
            INSERT INTO master_db.clients_master
              (client_name, domain_postfix, db_name, db_host, db_engine, created_at)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (client_name, tenant_domain_postfix, db_name, '127.0.0.1', 'mysql', timezone.now()))

        admin_cur.execute("SELECT * FROM master_db.clients_master WHERE db_name=%s LIMIT 1", (db_name,))
        client_row = admin_cur.fetchone()

        admin_cur.close()
        admin_conn.close()

    except Exception as e:
        messages.error(request, f"Error writing to master_db.clients_master: {e}")
        try:
            admin_cur.close()
        except Exception:
            pass
        try:
            admin_conn.close()
        except Exception:
            pass
        return redirect('new_tenant')

    # Provision tenant DB + user
    try:
        init = DBInitializer()
        tenant_user, tenant_pwd = init.create_db_and_user(client_row)
    except Exception as e:
        messages.error(request, f"Error creating tenant DB/user: {e}")
        return redirect('new_tenant')

    # Run DDL / seed roles
    try:
        init.run_ddl_on_tenant(client_row['db_name'], tenant_user, tenant_pwd)
        init.seed_roles_and_permissions(client_row['db_name'], tenant_user, tenant_pwd)
    except Exception as e:
        messages.error(request, f"Error running tenant DDL / seeding roles: {e}")
        return redirect('new_tenant')

    # Create initial tenant admin
    temp_admin_pw = _rand_password(12)
    admin_email = f"admin@{domain}"

    try:
        tenant_conn = pymysql.connect(
            host=ADMIN_CONF['host'],
            port=ADMIN_CONF['port'],
            user=tenant_user,
            password=tenant_pwd,
            database=db_name,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )
        tcur = tenant_conn.cursor()

        # Insert or update admin
        tcur.execute("SELECT id FROM users WHERE email=%s LIMIT 1", (admin_email,))
        found = tcur.fetchone()
        if not found:
            hashed = hash_password(temp_admin_pw)
            tcur.execute("""
                INSERT INTO users (email, full_name, password_hash, role, is_active, created_at)
                VALUES (%s,%s,%s,%s,1,NOW())
            """, (admin_email, "Tenant Admin", hashed, "Admin"))
        else:
            tcur.execute("UPDATE users SET password_hash=%s, role=%s WHERE email=%s",
                         (hash_password(temp_admin_pw), "Admin", admin_email))

        # Ensure members record exists
        tcur.execute("""
            INSERT IGNORE INTO members (email, first_name, last_name, phone, meta, created_by, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,NOW())
        """, (admin_email, "Tenant", "Admin", None, None, None))

        # Get member_id and role_id
        tcur.execute("SELECT id FROM members WHERE email=%s LIMIT 1", (admin_email,))
        mrow = tcur.fetchone()
        member_id = mrow['id'] if mrow else None

        tcur.execute("SELECT id FROM roles WHERE name='Admin' LIMIT 1")
        rrow = tcur.fetchone()
        role_admin_id = rrow['id'] if rrow else None

        # Assign role
        if member_id and role_admin_id:
            tcur.execute("""
                INSERT IGNORE INTO tenant_role_assignments (member_id, role_id, assigned_by, assigned_at)
                VALUES (%s,%s,%s,NOW())
            """, (member_id, role_admin_id, member_id))

        tcur.close()
        tenant_conn.close()
    except Exception as e:
        messages.error(request, f"Error creating tenant admin user: {e}")
        return redirect('new_tenant')

    # Update master with user/pass
    try:
        admin_conn = pymysql.connect(**ADMIN_CONF, cursorclass=pymysql.cursors.DictCursor, autocommit=True)
        cur = admin_conn.cursor()
        cur.execute("""
            UPDATE master_db.clients_master SET db_user=%s, db_password=%s WHERE id=%s
        """, (tenant_user, tenant_pwd, client_row['id']))
        cur.close()
        admin_conn.close()
    except Exception:
        pass

    # Success message
    messages.success(request, f"Tenant {client_name} created. Admin account: {admin_email}")
    messages.info(request, f"Temporary admin password: {temp_admin_pw} (please change immediately)")

    return redirect('new_tenant')



