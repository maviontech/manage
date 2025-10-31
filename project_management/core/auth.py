# auth.py
import os
import pymysql
import bcrypt
from core.db_connector import get_connection_from_config

# MASTER DB connection config read from environment (or you can hardcode)
MASTER_DB_CONFIG = {
    'db_engine': 'mysql',
    'db_host': os.environ.get('MYSQL_ADMIN_HOST', '127.0.0.1'),
    'db_port': int(os.environ.get('MYSQL_ADMIN_PORT') or 3306),
    'db_user': os.environ.get('MYSQL_ADMIN_USER', 'root'),
    'db_password': os.environ.get('MYSQL_ADMIN_PWD', 'root'),
    'db_name': os.environ.get('MASTER_DB_NAME', 'master_db')
}

def hash_password(plain_password: str) -> str:
    hashed = bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')

def check_password(plain_password: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed.encode('utf-8'))

def identify_tenant_by_email(email: str):
    postfix = email.split('@')[-1]
    conn = pymysql.connect(
        host=MASTER_DB_CONFIG['db_host'],
        port=MASTER_DB_CONFIG['db_port'],
        user=MASTER_DB_CONFIG['db_user'],
        password=MASTER_DB_CONFIG['db_password'],
        database=MASTER_DB_CONFIG['db_name'],
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )
    cur = conn.cursor()
    cur.execute("SELECT * FROM clients_master WHERE domain_postfix = %s", ('@' + postfix,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row  # None or dict with client metadata

def authenticate(email: str, password: str, tenant_ident: dict):
    """
    tenant_ident is a dict from identify_tenant_by_email (must contain db_name, db_user, db_password, db_host, db_port)
    Returns user dict or None
    """
    # Build tenant connection config. If master stored db_user/password, use them;
    # else, tenant_ident might only have db_name and we assume tenant user exists with same credentials (not recommended).
    conn_conf = {
        'db_engine': 'mysql',
        'db_name': tenant_ident.get('db_name'),
        'db_host': tenant_ident.get('db_host') or MASTER_DB_CONFIG['db_host'],
        'db_port': tenant_ident.get('db_port') or MASTER_DB_CONFIG['db_port'],
        'db_user': tenant_ident.get('db_user'),
        'db_password': tenant_ident.get('db_password')
    }
    # If tenant DB user/password not present in master row, fail early
    if not conn_conf['db_user'] or not conn_conf['db_password']:
        raise RuntimeError("Tenant DB credentials not present for tenant; run initializer to provision them.")

    conn = get_connection_from_config(conn_conf)
    cur = conn.cursor()
    cur.execute("SELECT id, email, full_name, password_hash, role, is_active FROM users WHERE email = %s", (email,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    if not check_password(password, row['password_hash']):
        return None
    return {
        'id': row['id'],
        'email': row['email'],
        'full_name': row.get('full_name'),
        'role': row.get('role'),
        'is_active': row.get('is_active')
    }
