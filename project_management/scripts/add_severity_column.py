"""
Add a `severity` column to the `tasks` table in every tenant database.

Background: severity used to be conflated with priority (bugs stored their
severity in the priority column, and the task view derived a severity label
from priority). This migration introduces a real, independently-editable
severity field. Idempotent — safe to run multiple times.

Usage (from the project_management directory):
    python scripts/add_severity_column.py
"""
import pymysql
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

MASTER_DB_CONFIG = {
    'db_host': os.environ.get('MYSQL_ADMIN_HOST', '127.0.0.1'),
    'db_port': int(os.environ.get('MYSQL_ADMIN_PORT') or 3306),
    'db_user': os.environ.get('MYSQL_ADMIN_USER', 'root'),
    'db_password': os.environ.get('MYSQL_ADMIN_PWD', 'root'),
    'db_name': os.environ.get('MASTER_DB_NAME', 'master_db'),
}


def add_severity_column():
    print("\n" + "=" * 70)
    print(" " * 18 + "ADD SEVERITY COLUMN TO tasks")
    print("=" * 70)

    print("\nConnecting to master database...")
    try:
        master_conn = pymysql.connect(
            host=MASTER_DB_CONFIG['db_host'], port=MASTER_DB_CONFIG['db_port'],
            user=MASTER_DB_CONFIG['db_user'], password=MASTER_DB_CONFIG['db_password'],
            database=MASTER_DB_CONFIG['db_name'], cursorclass=pymysql.cursors.DictCursor,
        )
    except Exception as e:
        print(f"FAILED to connect to master database: {e}")
        return 1

    ok, err = 0, 0
    try:
        with master_conn.cursor() as cur:
            cur.execute("SELECT id, client_name, db_name, db_host, db_port, db_user, db_password FROM clients_master")
            tenants = cur.fetchall()

        if not tenants:
            print("No tenants found in master database.")
            return 0

        print(f"Found {len(tenants)} tenant(s)\n" + "-" * 70)
        for t in tenants:
            name = t.get('client_name'); db = t.get('db_name')
            try:
                tconn = pymysql.connect(
                    host=t.get('db_host') or MASTER_DB_CONFIG['db_host'],
                    port=int(t.get('db_port') or MASTER_DB_CONFIG['db_port']),
                    user=t.get('db_user'), password=t.get('db_password'),
                    database=db, autocommit=True,
                )
                with tconn.cursor() as c:
                    c.execute("DESCRIBE tasks")
                    cols = [r[0] for r in c.fetchall()]
                    if 'severity' in cols:
                        print(f"  = {name} ({db}): severity already exists — skipped")
                    else:
                        c.execute("ALTER TABLE tasks ADD COLUMN severity VARCHAR(20) NULL")
                        print(f"  + {name} ({db}): severity column added")
                        ok += 1
                tconn.close()
            except Exception as e:
                err += 1
                print(f"  ! {name} ({db}): ERROR — {e}")
    finally:
        master_conn.close()

    print("\n" + "=" * 70)
    print(f"Done. Columns added: {ok}, errors: {err}")
    print("=" * 70)
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(add_severity_column())
