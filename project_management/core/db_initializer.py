# db_initializer.py
import os
import pymysql
import secrets
import string
from core.auth import hash_password

MASTER_DB = os.environ.get('MASTER_DB_NAME', 'master_db')
ADMIN_HOST = os.environ.get('MYSQL_ADMIN_HOST', '127.0.0.1')
ADMIN_PORT = int(os.environ.get('MYSQL_ADMIN_PORT', 3306))
ADMIN_USER = os.environ.get('MYSQL_ADMIN_USER', 'root')
ADMIN_PWD = os.environ.get('MYSQL_ADMIN_PWD', '')

TENANT_DDL = [
    """
    CREATE TABLE IF NOT EXISTS users (
      id INT AUTO_INCREMENT PRIMARY KEY,
      email VARCHAR(255) NOT NULL UNIQUE,
      full_name VARCHAR(255),
      password_hash VARCHAR(255) NOT NULL,
      role VARCHAR(50),
      is_active TINYINT(1) DEFAULT 1,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS projects (
      id INT AUTO_INCREMENT PRIMARY KEY,
      name VARCHAR(255) NOT NULL,
      description TEXT,
      start_date DATE,
      end_date DATE,
      status VARCHAR(50),
      created_by INT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS subprojects (
      id INT AUTO_INCREMENT PRIMARY KEY,
      project_id INT,
      name VARCHAR(255) NOT NULL,
      description TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS tasks (
      id INT AUTO_INCREMENT PRIMARY KEY,
      project_id INT,
      subproject_id INT,
      title VARCHAR(300) NOT NULL,
      description TEXT,
      status VARCHAR(50),
      priority VARCHAR(20),
      assigned_to INT,
      created_by INT,
      due_date DATE,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS time_entries (
      id INT AUTO_INCREMENT PRIMARY KEY,
      task_id INT,
      user_id INT,
      hours DOUBLE,
      date DATE,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS comments (
      id INT AUTO_INCREMENT PRIMARY KEY,
      task_id INT,
      commenter_id INT,
      comment_text TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS activity_log (
      id INT AUTO_INCREMENT PRIMARY KEY,
      entity_type VARCHAR(80),
      entity_id INT,
      action VARCHAR(150),
      performed_by INT,
      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    """
    CREATE TABLE IF NOT EXISTS members (
      id INT AUTO_INCREMENT PRIMARY KEY,
      email VARCHAR(255) NOT NULL,
      first_name VARCHAR(120),
      last_name VARCHAR(120),
      phone VARCHAR(50),
      meta JSON DEFAULT NULL,
      created_by INT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE KEY uk_member_email (email)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    """
    CREATE TABLE IF NOT EXISTS teams (
      id INT AUTO_INCREMENT PRIMARY KEY,
      name VARCHAR(255) NOT NULL,
      slug VARCHAR(255) UNIQUE,
      description TEXT,
      team_lead_id INT DEFAULT NULL,   -- FK to members.id for team lead
      created_by INT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (team_lead_id) REFERENCES members(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
     """
    CREATE TABLE IF NOT EXISTS members (
      id INT AUTO_INCREMENT PRIMARY KEY,
      email VARCHAR(255) NOT NULL,
      first_name VARCHAR(120),
      last_name VARCHAR(120),
      phone VARCHAR(50),
      meta JSON DEFAULT NULL,
      created_by INT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE KEY uk_member_email (email)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    """
    CREATE TABLE IF NOT EXISTS team_memberships (
      id INT AUTO_INCREMENT PRIMARY KEY,
      team_id INT NOT NULL,
      member_id INT NOT NULL,
      team_role VARCHAR(50) DEFAULT 'Member', -- Member, Lead, etc.
      added_by INT,
      added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE KEY uk_team_member (team_id, member_id),
      FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
      FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
]

def random_password(length=18):
    alphabet = string.ascii_letters + string.digits + "-_!@#"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

class DBInitializer:
    def __init__(self):
        self.admin_conn = pymysql.connect(
            host=ADMIN_HOST, port=ADMIN_PORT, user=ADMIN_USER, password=ADMIN_PWD,
            cursorclass=pymysql.cursors.DictCursor, autocommit=True
        )

    def get_clients(self):
        cur = self.admin_conn.cursor()
        cur.execute(f"SELECT * FROM {MASTER_DB}.clients_master WHERE db_engine='mysql'")
        rows = cur.fetchall()
        cur.close()
        return rows

    def create_db_and_user(self, client):
        db_name = client['db_name']
        tenant_user = f"tenant_{client['id']}"
        tenant_pwd = random_password()

        cur = self.admin_conn.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        # Create/alter user
        # Try CREATE USER IF NOT EXISTS (MySQL 5.7+), else fallback to CREATE and catch errors
        try:
            cur.execute(f"CREATE USER IF NOT EXISTS '{tenant_user}'@'%' IDENTIFIED BY %s;", (tenant_pwd,))
        except Exception:
            # fallback: attempt create; if fails try alter
            try:

                cur.execute(f"CREATE USER '{tenant_user}'@'%' IDENTIFIED BY '{tenant_pwd}';")
            except Exception:
                # Python
                # Python
                query = f"ALTER USER '{tenant_user}'@'%' IDENTIFIED BY '{tenant_pwd}';"
                cur.execute(query)
        # Grant
        cur.execute(f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{tenant_user}'@'%';")
        cur.execute("FLUSH PRIVILEGES;")
        # update master_db credentials
        cur.execute(f"UPDATE {MASTER_DB}.clients_master SET db_user=%s, db_password=%s WHERE id=%s;", (tenant_user, tenant_pwd, client['id']))
        print(f"[init] Created DB `{db_name}` and user `{tenant_user}` for client id {client['id']}.")
        return tenant_user, tenant_pwd

    def run_ddl_on_tenant(self, db_name, tenant_user, tenant_pwd):
        conn = pymysql.connect(
            host=ADMIN_HOST, port=ADMIN_PORT, user=tenant_user, password=tenant_pwd,
            database=db_name, cursorclass=pymysql.cursors.DictCursor, autocommit=True
        )
        cur = conn.cursor()
        for ddl in TENANT_DDL:
            cur.execute(ddl)
        cur.close()
        conn.close()
        print(f"[init] Tenant DDL executed on {db_name}")

    def seed_admin(self, db_name, tenant_user, tenant_pwd, domain_postfix):
        conn = pymysql.connect(
            host=ADMIN_HOST, port=ADMIN_PORT, user=tenant_user, password=tenant_pwd,
            database=db_name, cursorclass=pymysql.cursors.DictCursor, autocommit=True
        )
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM users;")
        row = cur.fetchone()
        cnt = row['c'] if row else 0
        if cnt == 0:
            domain = domain_postfix.lstrip('@')
            admin_email = f"admin@{domain}"
            pw = "admin123"
            hashed = hash_password(pw)
            cur.execute("INSERT INTO users (email, full_name, password_hash, role, is_active) VALUES (%s,%s,%s,%s,%s)",
                        (admin_email, "Tenant Admin", hashed, "Admin", 1))
            print(f"[init] Seeded admin {admin_email} with password 'admin123' in {db_name}")
        cur.close()
        conn.close()

    def run(self):
        clients = self.get_clients()
        if not clients:
            print("[init] No clients found in master_db.clients_master. Insert client rows first.")
            return
        for client in clients:
            # if db_user present skip creation steps (idempotent)
            if client.get('db_user'):
                print(f"[init] client id {client['id']} already has db_user {client['db_user']}; using stored credentials.")
                tenant_user, tenant_pwd = client['db_user'], client['db_password']
            else:
                tenant_user, tenant_pwd = self.create_db_and_user(client)
            # run DDL
            try:
                self.run_ddl_on_tenant(client['db_name'], tenant_user, tenant_pwd)
                self.seed_admin(client['db_name'], tenant_user, tenant_pwd, client['domain_postfix'])
            except Exception as e:
                print("[init] Error provisioning tenant:", e)
        print("[init] Done provisioning all tenants.")

if __name__ == "__main__":
    # validate admin creds presence
    if not ADMIN_PWD:
        import getpass
        ADMIN_PWD = getpass.getpass("MySQL admin password: ")
    print("[init] Connecting to MySQL admin at", ADMIN_HOST)
    init = DBInitializer()
    init.run()
