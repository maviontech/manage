"""
Migration script to add tenant_work_types table to master_db.
This table stores which work types are enabled for each tenant.
"""

import pymysql

ADMIN_CONF = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': 'root'
}

def create_tenant_work_types_table():
    """Create tenant_work_types table in master_db"""
    try:
        conn = pymysql.connect(
            host=ADMIN_CONF['host'],
            port=ADMIN_CONF['port'],
            user=ADMIN_CONF['user'],
            password=ADMIN_CONF['password'],
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )
        cur = conn.cursor()

        # Create master_db if not exists
        cur.execute("CREATE DATABASE IF NOT EXISTS master_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        
        # Create tenant_work_types table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS master_db.tenant_work_types (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                tenant_id BIGINT UNSIGNED NOT NULL,
                work_type VARCHAR(50) NOT NULL,
                is_enabled BOOLEAN DEFAULT TRUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (tenant_id) REFERENCES master_db.clients_master(id) ON DELETE CASCADE,
                UNIQUE KEY ux_tenant_work_type (tenant_id, work_type),
                INDEX idx_tenant_id (tenant_id),
                INDEX idx_work_type (work_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        
        print("✓ Table master_db.tenant_work_types created successfully")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"✗ Error creating tenant_work_types table: {e}")
        raise

if __name__ == '__main__':
    print("Creating tenant_work_types table in master_db...")
    create_tenant_work_types_table()
    print("Migration completed!")
