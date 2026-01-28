# auth.py
import os
import pymysql
import logging
import bcrypt
from core.db_connector import get_connection_from_config

# Try to use Django's check_password if available (helps support Django-formatted hashes)
try:
    from django.contrib.auth.hashers import check_password as django_check_password
    HAS_DJANGO_HASHERS = True
except Exception:
    django_check_password = None
    HAS_DJANGO_HASHERS = False
logger = logging.getLogger('project_management')
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
    """
    Hash using bcrypt and return a utf-8 string suitable for storage.
    """
    if not isinstance(plain_password, str):
        plain_password = str(plain_password)
    hashed = bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt(rounds=12))
    return hashed.decode('utf-8')

def _looks_like_bcrypt(s: str) -> bool:
    return isinstance(s, str) and s.startswith(('$2a$', '$2b$', '$2y$'))

def check_password(plain_password: str, stored_hash: str):
    """
    Robust check that supports:
      - bcrypt (preferred)
      - Django built-in hashers (pbkdf2, argon2, etc.) when available
      - legacy hex digests (example included for SHA1/MD5)
    Returns: (ok: bool, needs_rehash: bool)
      needs_rehash==True => stored_hash was not bcrypt (caller can rehash and store bcrypt)
    """
    if not stored_hash:
        return False, False

    # 1) bcrypt (fast path)
    try:
        if _looks_like_bcrypt(stored_hash):
            ok = bcrypt.checkpw(plain_password.encode('utf-8'), stored_hash.encode('utf-8'))
            return bool(ok), False
    except ValueError as e:
        # invalid salt or other bcrypt format error — log and continue to fallbacks
        logger.warning("bcrypt.checkpw ValueError: %s", e)

    # 2) Django hashers (if available) - supports many formats
    try:
        if HAS_DJANGO_HASHERS:
            try:
                ok = django_check_password(plain_password, stored_hash)
                if ok:
                    # stored_hash is not bcrypt — recommend rehash to bcrypt
                    return True, True
            except Exception as e:
                logger.debug("django_check_password failed: %s", e)
    except Exception:
        pass

    # 3) Example legacy SHA1 or MD5 storage (customize to your legacy format)
    #    Suppose old storage was hex digest of sha1: "sha1$<hex>"
    try:
        if isinstance(stored_hash, str) and stored_hash.startswith('sha1$'):
            import hashlib
            hexpart = stored_hash.split('$',1)[1]
            cand = hashlib.sha1(plain_password.encode('utf-8')).hexdigest()
            if cand == hexpart:
                return True, True
        if isinstance(stored_hash, str) and stored_hash.startswith('md5$'):
            import hashlib
            hexpart = stored_hash.split('$',1)[1]
            if hashlib.md5(plain_password.encode('utf-8')).hexdigest() == hexpart:
                return True, True
    except Exception as e:
        logger.debug("legacy check failed: %s", e)

    # 4) last-resort: direct equality (not recommended) — keep disabled unless you know stored plaintext
    # if plain_password == stored_hash:
    #     return True, True

    return False, False

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
        logger.debug("authenticate: no user found for email=%s", email)
        logger.info(f"auth: no user for {email}")
        return None
    stored_hash = row.get('password_hash') if isinstance(row, dict) else (row[3] if len(row) > 3 else None)
    logger.debug("authenticate: user found email=%s stored_hash_prefix=%s", email, (stored_hash[:6] if isinstance(stored_hash, str) else 'none'))
    logger.info(f"auth: user found {email} hash_prefix={(stored_hash[:6] if isinstance(stored_hash, str) else 'none')}")
    ok, needs_rehash = check_password(password, stored_hash)
    logger.debug("authenticate: password check result ok=%s needs_rehash=%s", ok, needs_rehash)
    logger.info(f"auth: password check ok={ok} needs_rehash={needs_rehash}")
    if not ok:
        logger.info("authenticate failed for %s: invalid password", email)
        logger.info(f"auth: invalid password for {email}")
        return None
    return {
        'id': row['id'],
        'email': row['email'],
        'full_name': row.get('full_name'),
        'role': row.get('role'),
        'is_active': row.get('is_active')
    }
