# db_initializer.py
import os
import pymysql
import secrets
import string
from core.auth import hash_password
import logging

# Use the 'utility' logger configured in settings.LOGGING
logger = logging.getLogger('utility')

MASTER_DB = os.environ.get('MASTER_DB_NAME', 'master_db')
ADMIN_HOST = os.environ.get('MYSQL_ADMIN_HOST', '127.0.0.1')
ADMIN_PORT = int(os.environ.get('MYSQL_ADMIN_PORT', 3306))
ADMIN_USER = os.environ.get('MYSQL_ADMIN_USER', 'root')
ADMIN_PWD = os.environ.get('MYSQL_ADMIN_PWD', 'root')


def initialize_master_database():
    """
    Initialize master database on server startup.
    Creates the database and all required tables if they don't exist.
    """
    try:
        # Connect without database to create it
        conn = pymysql.connect(
            host=ADMIN_HOST,
            port=ADMIN_PORT,
            user=ADMIN_USER,
            password=ADMIN_PWD,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )
        cur = conn.cursor()
        logger.info(f"✓ Successfully connected to MySQL server")
        # Create master_db if it doesn't exist
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {MASTER_DB} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        logger.info(f"✓ Successfully connected to MySQL database: {MASTER_DB}")
        
        # Now connect to the master_db
        cur.execute(f"USE {MASTER_DB}")
        
        # Create clients_master table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS clients_master (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                client_name VARCHAR(255) NOT NULL,
                domain_postfix VARCHAR(255) NOT NULL UNIQUE,
                db_name VARCHAR(255) NOT NULL UNIQUE,
                db_host VARCHAR(100) DEFAULT '127.0.0.1',
                db_engine VARCHAR(50) DEFAULT 'mysql',
                db_user VARCHAR(255),
                db_password VARCHAR(255),
                created_at DATETIME,
                updated_at DATETIME,
                INDEX idx_domain (domain_postfix),
                INDEX idx_db_name (db_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        
        # Create tenants_admin table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tenants_admin (
                id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                first_name VARCHAR(100) NOT NULL,
                last_name VARCHAR(100) NOT NULL,
                email VARCHAR(255) NOT NULL UNIQUE,
                phone VARCHAR(50),
                admin_username VARCHAR(150) NOT NULL UNIQUE,
                admin_password VARCHAR(255) NOT NULL,
                notes TEXT,
                permissions TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_email (email),
                INDEX idx_admin_username (admin_username)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        
        # Create tenant_work_types table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tenant_work_types (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                tenant_id BIGINT UNSIGNED NOT NULL,
                work_type VARCHAR(50) NOT NULL,
                is_enabled TINYINT(1) DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (tenant_id) REFERENCES clients_master(id) ON DELETE CASCADE,
                UNIQUE KEY ux_tenant_work_type (tenant_id, work_type),
                INDEX idx_tenant_id (tenant_id),
                INDEX idx_work_type (work_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        
        logger.info(f"✓ Tenant management tables created or already exist.")
        
        # Create default tenant admin if not exists
        cur.execute("SELECT COUNT(*) AS cnt FROM tenants_admin WHERE admin_username = 'tenant'")
        result = cur.fetchone()
        if result['cnt'] == 0:
            # Hash the password
            hashed_password = hash_password('tenant')
            
            # Insert default tenant admin
            cur.execute("""
                INSERT INTO tenants_admin 
                (first_name, last_name, email, admin_username, admin_password, notes) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                'Tenant',
                'Admin',
                'tenant@admin.com',
                'tenant',
                hashed_password,
                'Default tenant admin account - please change password after first login'
            ))
        cur.close()
        conn.close()
        
    except pymysql.Error as e:
        logger.error(f"✗ MySQL Error: {e}")
    except Exception as e:
        logger.error(f"✗ Error initializing master database: {e}")

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
      CREATE TABLE IF NOT EXISTS employees (
        id INT AUTO_INCREMENT PRIMARY KEY,
        employee_code VARCHAR(50) UNIQUE NOT NULL,
        email VARCHAR(255) NOT NULL,
        first_name VARCHAR(120) NOT NULL,
        last_name VARCHAR(120),
        phone VARCHAR(50),
        department VARCHAR(100),
        designation VARCHAR(100),
        date_of_joining DATE,
        date_of_birth DATE,
        address TEXT,
        city VARCHAR(100),
        state VARCHAR(100),
        country VARCHAR(100),
        postal_code VARCHAR(20),
        emergency_contact_name VARCHAR(255),
        emergency_contact_phone VARCHAR(50),
        status ENUM('Active', 'Inactive', 'On Leave', 'Terminated') DEFAULT 'Active',
        salary DECIMAL(10, 2),
        created_by INT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uk_employee_email (email),
        INDEX idx_employee_code (employee_code),
        INDEX idx_employee_status (status)
      ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
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
        city VARCHAR(100),
        dob DATE,
        address TEXT,
        profile_photo VARCHAR(512),
        UNIQUE KEY uk_member_email (email)
      ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS member_social_links (
      id INT AUTO_INCREMENT PRIMARY KEY,
      member_id INT NOT NULL,
      github_url VARCHAR(255),
      twitter_url VARCHAR(255),
      facebook_url VARCHAR(255),
      linkedin_url VARCHAR(255),
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      UNIQUE KEY uk_member_social (member_id),
      FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    # """
    # CREATE TABLE IF NOT EXISTS members (
    #   id INT AUTO_INCREMENT PRIMARY KEY,
    #   email VARCHAR(255) NOT NULL,
    #   first_name VARCHAR(120),
    #   last_name VARCHAR(120),
    #   phone VARCHAR(50),
    #   meta JSON DEFAULT NULL,
    #   created_by INT,
    #   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    #   city VARCHAR(100),
    #   dob DATE,
    #   address TEXT,
    #   UNIQUE KEY uk_member_email (email)
    # ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    # """,
    """
    CREATE TABLE IF NOT EXISTS projects (
      id INT AUTO_INCREMENT PRIMARY KEY,
      name VARCHAR(255) NOT NULL,
      description TEXT,
      start_date DATE,
      tentative_end_date DATE,
      end_date DATETIME,
      status VARCHAR(50),
      employee_id INT,
      created_by INT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS project_statuses (
      id INT AUTO_INCREMENT PRIMARY KEY,
      project_id INT NOT NULL,
      status_name VARCHAR(100) NOT NULL,
      status_order INT DEFAULT 0,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
      INDEX idx_project_status (project_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS project_work_types (
      id INT AUTO_INCREMENT PRIMARY KEY,
      project_id INT NOT NULL,
      work_type VARCHAR(50) NOT NULL,
      is_enabled TINYINT(1) DEFAULT 1,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
      INDEX idx_project_worktype (project_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS subprojects (
      id INT AUTO_INCREMENT PRIMARY KEY,
      project_id INT,
      name VARCHAR(255) NOT NULL,
      description TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      start_date DATE,
      end_date DATE,
      status VARCHAR(50) DEFAULT 'Active',
      created_by INT,
      FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
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
      assigned_type ENUM('member','team') DEFAULT 'member',
      assigned_to INT,
      created_by INT,
      due_date DATE,
      work_type VARCHAR(50) DEFAULT 'Task',
      si_browser VARCHAR(255) DEFAULT NULL,
      si_resolution VARCHAR(50) DEFAULT NULL,
      si_os VARCHAR(100) DEFAULT NULL,
      si_timestamp VARCHAR(50) DEFAULT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      closure_date DATE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    """,
    """
    CREATE TABLE IF NOT EXISTS time_entries (
      id INT AUTO_INCREMENT PRIMARY KEY,
      task_id INT,
      user_id INT,
      hours DOUBLE,
      date DATE,
      description TEXT,
      status ENUM('pending', 'approved', 'rejected') DEFAULT 'pending',
      approved_by INT,
      approved_at TIMESTAMP NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL,
      FOREIGN KEY (user_id) REFERENCES members(id) ON DELETE CASCADE,
      FOREIGN KEY (approved_by) REFERENCES members(id) ON DELETE SET NULL,
      INDEX idx_user_id (user_id),
      INDEX idx_task_id (task_id),
      INDEX idx_status (status),
      INDEX idx_date (date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS timer_sessions (
      id INT AUTO_INCREMENT PRIMARY KEY,
      user_id INT NOT NULL,
      task_id INT,
      start_time DATETIME NOT NULL,
      end_time DATETIME,
      duration_seconds INT DEFAULT 0,
      is_running TINYINT(1) DEFAULT 1,
      paused TINYINT(1) DEFAULT 0,
      paused_at DATETIME NULL,
      paused_duration INT DEFAULT 0,
      notes TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      FOREIGN KEY (user_id) REFERENCES members(id) ON DELETE CASCADE,
      FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL,
      INDEX idx_user_id (user_id),
      INDEX idx_task_id (task_id),
      INDEX idx_is_running (is_running)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS task_comments (
      id INT AUTO_INCREMENT PRIMARY KEY,
      task_id INT NOT NULL,
      comment_text TEXT NOT NULL,
      commenter_id INT NOT NULL,
      commenter_name VARCHAR(255),
      is_internal BOOLEAN DEFAULT FALSE,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
      FOREIGN KEY (commenter_id) REFERENCES members(id) ON DELETE CASCADE,
      INDEX idx_task (task_id),
      INDEX idx_commenter (commenter_id),
      INDEX idx_created (created_at)
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
    """,
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
    """,

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
    """,
"""
-- Roles & permissions
CREATE TABLE IF NOT EXISTS roles (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  description VARCHAR(255),
  is_builtin TINYINT(1) DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_role_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
""",
"""
CREATE TABLE IF NOT EXISTS permissions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(150) NOT NULL,
  description VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_perm_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
""",
"""
CREATE TABLE IF NOT EXISTS role_permissions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  role_id INT NOT NULL,
  permission_id INT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_role_perm (role_id, permission_id),
  CONSTRAINT fk_rp_role FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
  CONSTRAINT fk_rp_perm FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
""",
"""
CREATE TABLE IF NOT EXISTS project_role_assignments (
  id INT AUTO_INCREMENT PRIMARY KEY,
  project_id INT NOT NULL,
  member_id INT NOT NULL,
  role_id INT NOT NULL,
  assigned_by INT DEFAULT NULL,
  assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_proj_mem_role (project_id, member_id, role_id),
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
  FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
  FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
""",
"""
CREATE TABLE IF NOT EXISTS password_reset_tokens (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  token VARCHAR(128) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMP NOT NULL,
  used TINYINT(1) DEFAULT 0,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE KEY uk_token (token)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
""",
"""
CREATE TABLE IF NOT EXISTS password_policies (
  id INT AUTO_INCREMENT PRIMARY KEY,
  min_length INT DEFAULT 8,
  require_upper TINYINT(1) DEFAULT 1,
  require_lower TINYINT(1) DEFAULT 1,
  require_number TINYINT(1) DEFAULT 1,
  require_symbol TINYINT(1) DEFAULT 0,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
""",
    """
CREATE TABLE IF NOT EXISTS tenant_role_assignments (
  id INT AUTO_INCREMENT PRIMARY KEY,
  member_id INT NOT NULL,
  role_id INT NOT NULL,
  assigned_by INT DEFAULT NULL,
  assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_tenant_member_role (member_id, role_id),
  KEY member_id_idx (member_id),
  KEY role_id_idx (role_id),
  CONSTRAINT fk_tr_member FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
  CONSTRAINT fk_tr_role   FOREIGN KEY (role_id)   REFERENCES roles(id)   ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
""",
    """
CREATE TABLE IF NOT EXISTS chat_conversation (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id VARCHAR(128) NOT NULL,
  user_a VARCHAR(128) NOT NULL,
  user_b VARCHAR(128) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY tenant_pair (tenant_id, user_a, user_b)
);
""",
    """
CREATE TABLE IF NOT EXISTS notifications (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  title VARCHAR(255) NOT NULL,
  message TEXT NOT NULL,
  type ENUM('info', 'success', 'warning', 'error', 'task', 'project', 'team') DEFAULT 'info',
  is_read TINYINT(1) DEFAULT 0,
  link VARCHAR(500),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_id (user_id),
  INDEX idx_is_read (is_read),
  INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
""",
    """

CREATE TABLE IF NOT EXISTS chat_message (
  id INT AUTO_INCREMENT PRIMARY KEY,
  conversation_id INT NOT NULL,
  sender VARCHAR(128) NOT NULL,
  text TEXT NOT NULL,
  is_read TINYINT(1) DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (conversation_id) REFERENCES chat_conversation(id) ON DELETE CASCADE
);
""",
    """

CREATE INDEX idx_msg_conv_created ON chat_message (conversation_id, created_at);
""",
    """
CREATE INDEX idx_conv_tenant ON chat_conversation (tenant_id);

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
        except Exception as e:
            # fallback: attempt create; if fails try alter
            logger.info(f"[init] CREATE USER failed for {tenant_user}, attempting ALTER USER. Error: {e}")
            try:

                cur.execute(f"CREATE USER '{tenant_user}'@'%' IDENTIFIED BY '{tenant_pwd}';")
            except Exception as e:
                # Python
                # Python
                logger.info(f"[init] ALTER USER for {tenant_user}. Error: {e}")
                query = f"ALTER USER '{tenant_user}'@'%' IDENTIFIED BY '{tenant_pwd}';"
                cur.execute(query)
        # Grant
        cur.execute(f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{tenant_user}'@'%';")
        cur.execute("FLUSH PRIVILEGES;")
        # update master_db credentials
        cur.execute(f"UPDATE {MASTER_DB}.clients_master SET db_user=%s, db_password=%s WHERE id=%s;", (tenant_user, tenant_pwd, client['id']))
        logger.info(f"[init] Created DB `{db_name}` and user `{tenant_user}` for client id {client['id']}.")
        return tenant_user, tenant_pwd

    def run_ddl_on_tenant(self, db_name, tenant_user, tenant_pwd):
        conn = pymysql.connect(
            host=ADMIN_HOST, port=ADMIN_PORT, user=tenant_user, password=tenant_pwd,
            database=db_name, cursorclass=pymysql.cursors.DictCursor, autocommit=True
        )
        cur = conn.cursor()
        try:
          for ddl in TENANT_DDL:
              cur.execute(ddl)
        except Exception as e:
          logger.error(f"[init] Error executing DDL on {db_name}: {e}")
          raise e
        cur.close()
        conn.close()
        logger.info(f"[init] Tenant DDL executed on {db_name}")
    def seed_roles_and_permissions(self, db_name, tenant_user, tenant_pwd):
        conn = pymysql.connect(
            host=ADMIN_HOST, port=ADMIN_PORT, user=tenant_user, password=tenant_pwd,
            database=db_name, cursorclass=pymysql.cursors.DictCursor, autocommit=True
        )
        cur = conn.cursor()

        # default permissions list
        perms = [
            ('projects.view', 'View projects'),
            ('projects.create', 'Create projects'),
            ('projects.edit', 'Edit projects'),
            ('projects.delete', 'Delete projects'),
            ('tasks.view', 'View tasks'),
            ('tasks.create', 'Create tasks'),
            ('tasks.edit', 'Edit tasks'),
            ('tasks.assign', 'Assign tasks'),
            ('tasks.delete', 'Delete tasks'),
            ('time.record', 'Record time'),
            ('time.approve', 'Approve time'),
            ('members.view', 'View members'),
            ('members.invite', 'Invite members'),
            ('members.remove', 'Remove members'),
            ('members.manage_roles', 'Manage member roles'),
            ('settings.view', 'View settings'),
            ('settings.edit', 'Edit settings'),
            ('roles.manage', 'Manage roles and permissions'),
            ('audit.view', 'View audit logs')
        ]

        # insert permissions idempotently
        for code, desc in perms:
            cur.execute("INSERT IGNORE INTO permissions (code, description) VALUES (%s,%s)", (code, desc))

        # create builtin roles
        builtin_roles = [
            ('Admin', 'Tenant-level admin with full control', 1),
            ('Developer', 'Developer role', 1),
            ('Tester', 'Tester role', 1),
            ('Collaborator', 'Collaborator role', 1),
            ('Viewer', 'Read-only', 1)
        ]
        for name, desc, builtin in builtin_roles:
            cur.execute("INSERT IGNORE INTO roles (name, description, is_builtin) VALUES (%s,%s,%s)",
                        (name, desc, builtin))

        # mapping: role -> permission codes (list)
        role_perm_map = {
            'Admin': [p[0] for p in perms],  # Admin gets everything
            'Developer': ['projects.view', 'tasks.view', 'tasks.create', 'tasks.edit', 'time.record', 'projects.edit'],
            'Tester': ['projects.view', 'tasks.view', 'tasks.create', 'tasks.edit', 'tasks.assign', 'time.record'],
            'Collaborator': ['projects.view', 'tasks.view', 'tasks.create', 'time.record'],
            'Viewer': ['projects.view', 'tasks.view']
        }

        # map role to permission ids
        # fetch role ids
        cur.execute("SELECT id, name FROM roles")
        roles_rows = cur.fetchall()
        role_ids = {r['name']: r['id'] for r in roles_rows}

        # fetch permission ids
        cur.execute("SELECT id, code FROM permissions")
        p_rows = cur.fetchall()
        perm_ids = {p['code']: p['id'] for p in p_rows}

        for role_name, codes in role_perm_map.items():
            r_id = role_ids.get(role_name)
            if not r_id:
                continue
            for code in codes:
                p_id = perm_ids.get(code)
                if not p_id:
                    continue
                # insert mapping idempotently
                cur.execute("INSERT IGNORE INTO role_permissions (role_id, permission_id) VALUES (%s,%s)", (r_id, p_id))

        # ensure a default password policy exists (only one row)
        cur.execute("SELECT COUNT(*) AS c FROM password_policies")
        if cur.fetchone()['c'] == 0:
            cur.execute(
                "INSERT INTO password_policies (min_length, require_upper, require_lower, require_number, require_symbol) VALUES (8,1,1,1,0)")

        cur.close()
        conn.close()
        logger.info(f"[init] Seeded roles & permissions for {db_name}")

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
            # Username and password are the same for first-time login
            username = "tenant"
            pw = "tenant"
            hashed = hash_password(pw)
            cur.execute("INSERT INTO users (email, full_name, password_hash, role, is_active) VALUES (%s,%s,%s,%s,%s)",
                        (admin_email, "Tenant Admin", hashed, "Admin", 1))
            logger.info(f"[init] Seeded admin {admin_email} with username 'tenant' and password 'tenant' in {db_name}")
        cur.close()
        conn.close()

    def run(self):
        clients = self.get_clients()
        if not clients:
            logger.info("[init] No clients found in master_db.clients_master. Insert client rows first.")
            return
        for client in clients:
            # if db_user present skip creation steps (idempotent)
            if client.get('db_user'):
                logger.info(f"[init] client id {client['id']} already has db_user {client['db_user']}; using stored credentials.")
                tenant_user, tenant_pwd = client['db_user'], client['db_password']
            else:
                tenant_user, tenant_pwd = self.create_db_and_user(client)
            # run DDL
            try:
                self.run_ddl_on_tenant(client['db_name'], tenant_user, tenant_pwd)
                self.seed_admin(client['db_name'], tenant_user, tenant_pwd, client['domain_postfix'])
                self.seed_roles_and_permissions(client['db_name'], tenant_user, tenant_pwd)
            except Exception as e:
                logger.error(f"[init] Error provisioning tenant: {e}")
        logger.info("[init] Done provisioning all tenants.")

if __name__ == "__main__":
# validate admin creds presence
    if not ADMIN_PWD:
        import getpass
        ADMIN_PWD = getpass.getpass("MySQL admin password: ")
    logger.info(f"[init] Connecting to MySQL admin at {ADMIN_HOST}")
    init = DBInitializer()
    init.run()
