
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
from .auth import hash_password, check_password  # same helper used in db_initializer

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
        admin_conn = pymysql.connect(**ADMIN_CONF)
        cur = admin_conn.cursor()
        cur.execute("""
            UPDATE master_db.clients_master SET db_user=%s, db_password=%s WHERE id=%s
        """, (tenant_user, tenant_pwd, client_row['id']))
        cur.close()
        admin_conn.close()
    except Exception:
        pass

    # Save work types configuration
    work_types = request.POST.getlist('work_types')
    if work_types:
        try:
            admin_conn = pymysql.connect(**ADMIN_CONF)
            cur = admin_conn.cursor()
            for work_type in work_types:
                cur.execute("""
                    INSERT INTO master_db.tenant_work_types (tenant_id, work_type, is_enabled, created_at)
                    VALUES (%s, %s, TRUE, NOW())
                    ON DUPLICATE KEY UPDATE is_enabled=TRUE, updated_at=NOW()
                """, (client_row['id'], work_type))
            cur.close()
            admin_conn.close()
        except Exception as e:
            messages.warning(request, f"Work types saved with some issues: {e}")

    # Success message
    messages.success(request, f"Tenant {client_name} created. Admin account: {admin_email}")
    messages.info(request, f"Temporary admin password: {temp_admin_pw} (please change immediately)")

    return redirect('new_tenant')


def multi_tenant_login_view(request):
    """
    Multi-tenant admin login page.
    Handles authentication against master_db.tenants_admin table.
    """
    if request.method == 'GET':
        # Clear any existing errors from session
        error = request.session.pop('multi_tenant_error', None)
        return render(request, 'core/Multi_tenant_login.html', {'error': error})
    
    # Handle POST - authentication
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '').strip()
    
    if not username or not password:
        request.session['multi_tenant_error'] = 'Username and password are required.'
        return redirect('multi_tenant_login')
    
    try:
        # Connect to master database and check tenants_admin table
        admin_conn = pymysql.connect(**ADMIN_CONF)
        cur = admin_conn.cursor()
        
        # Query tenants_admin table
        cur.execute("""
            SELECT id, first_name, last_name, email, admin_username, admin_password
            FROM master_db.tenants_admin
            WHERE admin_username = %s
            LIMIT 1
        """, (username,))
        
        admin_user = cur.fetchone()
        cur.close()
        admin_conn.close()
        
        if not admin_user:
            request.session['multi_tenant_error'] = 'Invalid credentials. Please try again.'
            return redirect('multi_tenant_login')
        
        # Verify password using check_password from auth.py
        stored_hash = admin_user['admin_password']
        ok, needs_rehash = check_password(password, stored_hash)
        
        if not ok:
            request.session['multi_tenant_error'] = 'Invalid credentials. Please try again.'
            return redirect('multi_tenant_login')
        
        # Authentication successful
        request.session['multi_tenant_admin'] = True
        request.session['admin_username'] = admin_user['admin_username']
        request.session['admin_id'] = admin_user['id']
        request.session['admin_email'] = admin_user['email']
        request.session['admin_full_name'] = f"{admin_user['first_name']} {admin_user['last_name']}"
        
        messages.success(request, f'Welcome, {admin_user["first_name"]} {admin_user["last_name"]}! You are now logged in as Tenant Administrator.')
        return redirect('tenant_dashboard')
        
    except Exception as e:
        request.session['multi_tenant_error'] = f'Authentication error: {str(e)}'
        return redirect('multi_tenant_login')


def tenant_dashboard_view(request):
    """
    Tenant dashboard - shows all tenants and management options.
    Requires multi-tenant admin authentication.
    """
    # Check if user is authenticated as multi-tenant admin
    if not request.session.get('multi_tenant_admin'):
        messages.warning(request, 'Please login to access the tenant dashboard.')
        return redirect('multi_tenant_login')
    
    # Get all tenants from master database
    tenants = []
    try:
        admin_conn = pymysql.connect(**ADMIN_CONF)
        cur = admin_conn.cursor()
        cur.execute("""
            SELECT id, client_name, domain_postfix, db_name, db_host, 
                   db_user, created_at, updated_at
            FROM master_db.clients_master
            ORDER BY created_at DESC
        """)
        tenants = cur.fetchall()
        cur.close()
        admin_conn.close()
    except Exception as e:
        messages.error(request, f"Error fetching tenants: {e}")
    
    context = {
        'tenants': tenants,
        'admin_username': request.session.get('admin_username', 'admin'),
    }
    
    return render(request, 'core/tenant_dashboard_v2.html', context)


def add_tenant_admin_view(request, tenant_id=None):
    """
    Add a new administrator to a specific tenant.
    Requires multi-tenant admin authentication.
    """
    # Check if user is authenticated as multi-tenant admin
    if not request.session.get('multi_tenant_admin'):
        messages.warning(request, 'Please login to access this page.')
        return redirect('multi_tenant_login')
    
    # Get all tenants for the dropdown
    tenants = []
    try:
        admin_conn = pymysql.connect(**ADMIN_CONF)
        cur = admin_conn.cursor()
        cur.execute("""
            SELECT id, client_name, domain_postfix, db_name, db_host, 
                   db_user, db_password
            FROM master_db.clients_master
            ORDER BY client_name ASC
        """)
        tenants = cur.fetchall()
        cur.close()
        admin_conn.close()
    except Exception as e:
        messages.error(request, f"Error fetching tenants: {e}")
        return redirect('tenant_dashboard')
    
    # Get specific tenant if tenant_id is provided
    tenant = None
    if tenant_id:
        tenant = next((t for t in tenants if t['id'] == tenant_id), None)
        if not tenant:
            messages.error(request, 'Tenant not found.')
            return redirect('tenant_dashboard')
    
    if request.method == 'GET':
        context = {
            'tenants': tenants,
            'tenant': tenant,
            'admin_username': request.session.get('admin_username', 'admin'),
        }
        return render(request, 'core/add_tenant_admin.html', context)
    
    # POST - Create new admin user
    admin_type = request.POST.get('admin_type', 'tenant_admin').strip()
    tenant_id_from_form = request.POST.get('tenant_id', '').strip()
    email = request.POST.get('email', '').strip()
    password = request.POST.get('password', '').strip()
    
    print(f"DEBUG: Creating admin - Type: {admin_type}, Email: {email}")  # Debug logging
    
    # Validate email format
    import re
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        messages.error(request, 'Invalid email format.')
        print(f"DEBUG: Invalid email format: {email}")  # Debug logging
        return redirect('add_tenant_admin')
    
    if admin_type == 'tenant_admin':
        # Create admin in master_db.tenants_admin table
        admin_username = request.POST.get('admin_username', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        
        if not admin_username or not first_name or not last_name or not email or not password:
            messages.error(request, 'All required fields must be filled for Tenant Admin.')
            print(f"DEBUG: Missing required fields - Username: {admin_username}, FirstName: {first_name}, LastName: {last_name}")  # Debug
            return redirect('add_tenant_admin')
        
        try:
            # Hash the password
            hashed = hash_password(password)
            
            print(f"DEBUG: Attempting to create tenant admin: {admin_username}")  # Debug logging
            
            # Connect to master database
            admin_conn = pymysql.connect(**ADMIN_CONF)
            cur = admin_conn.cursor()
            
            # Check if username or email already exists
            cur.execute("""
                SELECT id FROM master_db.tenants_admin 
                WHERE admin_username=%s OR email=%s LIMIT 1
            """, (admin_username, email))
            existing = cur.fetchone()
            
            if existing:
                messages.error(request, f'Tenant admin with username "{admin_username}" or email "{email}" already exists.')
                print(f"DEBUG: Duplicate found - Username: {admin_username}, Email: {email}")  # Debug
                cur.close()
                admin_conn.close()
                return redirect('add_tenant_admin')
            
            # Insert into tenants_admin table
            cur.execute("""
                INSERT INTO master_db.tenants_admin 
                (first_name, last_name, email, phone, admin_username, admin_password, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, (first_name, last_name, email, phone, admin_username, hashed))
            
            admin_conn.commit()  # Commit the transaction
            cur.close()
            admin_conn.close()
            
            print(f"DEBUG: Successfully created tenant admin: {admin_username}")  # Debug logging
            
            messages.success(request, 
                f'Tenant Administrator {first_name} {last_name} (username: {admin_username}) has been created successfully. '
                f'They can now login to the tenant management console.')
            return redirect('tenant_dashboard')
            
        except Exception as e:
            messages.error(request, f"Error creating tenant admin: {e}")
            print(f"DEBUG: Exception creating tenant admin: {str(e)}")  # Debug logging
            return redirect('add_tenant_admin')
    
    else:  # company_user
        # Create user in tenant's database
        full_name = request.POST.get('full_name', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        user_role = request.POST.get('user_role', 'User').strip()  # Get selected role, default to 'User'
        
        if not tenant_id_from_form:
            messages.error(request, 'Please select a tenant.')
            return redirect('add_tenant_admin')
        
        if not email or not full_name or not password:
            messages.error(request, 'Email, full name, and password are required.')
            return redirect('add_tenant_admin')
        
        # Validate role
        valid_roles = ['Admin', 'User', 'Manager', 'Viewer']
        if user_role not in valid_roles:
            user_role = 'User'  # Default to User if invalid role
        
        # Get the selected tenant
        tenant = next((t for t in tenants if str(t['id']) == tenant_id_from_form), None)
        if not tenant:
            messages.error(request, 'Selected tenant not found.')
            return redirect('add_tenant_admin')
        
        try:
            # Connect to tenant database
            tenant_conn = pymysql.connect(
                host=tenant['db_host'],
                port=ADMIN_CONF['port'],
                user=tenant['db_user'],
                password=tenant['db_password'],
                database=tenant['db_name'],
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True
            )
            tcur = tenant_conn.cursor()
            
            # Check if user already exists
            tcur.execute("SELECT id FROM users WHERE email=%s LIMIT 1", (email,))
            existing_user = tcur.fetchone()
            
            if existing_user:
                messages.error(request, f'User with email {email} already exists in {tenant["client_name"]}.')
                tcur.close()
                tenant_conn.close()
                return redirect('add_tenant_admin')
            
            # Hash the password
            hashed = hash_password(password)
            
            # Insert new user with email as username and selected role
            tcur.execute("""
                INSERT INTO users (email, full_name, password_hash, role, is_active, created_at)
                VALUES (%s, %s, %s, %s, 1, NOW())
            """, (email, full_name, hashed, user_role))
            
            # Get the inserted user ID
            user_id = tcur.lastrowid
            
            # Insert into members table
            tcur.execute("""
                INSERT INTO members (email, first_name, last_name, phone, meta, created_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, (email, first_name or full_name.split()[0], last_name or '', None, None, user_id))
            
            # Get member_id
            member_id = tcur.lastrowid
            
            # Get role_id for the selected role
            tcur.execute("SELECT id FROM roles WHERE name=%s LIMIT 1", (user_role,))
            role_row = tcur.fetchone()
            role_id = role_row['id'] if role_row else None
            
            # Assign the selected role to the new user
            if member_id and role_id:
                tcur.execute("""
                    INSERT INTO tenant_role_assignments (member_id, role_id, assigned_by, assigned_at)
                    VALUES (%s, %s, %s, NOW())
                """, (member_id, role_id, member_id))
            
            tcur.close()
            tenant_conn.close()
            
            messages.success(request, f'{user_role} user {full_name} ({email}) has been added to {tenant["client_name"]}. They can now login at the tenant login page using their email and password.')
            return redirect('tenant_dashboard')
            
        except Exception as e:
            messages.error(request, f"Error creating company user: {e}")
            return redirect('add_tenant_admin')
