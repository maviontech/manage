# scripts/create_master_db.py
import sqlite3
conn = sqlite3.connect('db_master.sqlite3')
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS clients_master (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_name TEXT,
  domain_postfix TEXT,
  db_name TEXT,
  db_host TEXT,
  db_user TEXT,
  db_password TEXT,
  db_engine TEXT,
  db_port INTEGER,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""")
conn.commit()
# Add sample client: sqlite tenant
cur.execute("INSERT INTO clients_master (client_name, domain_postfix, db_name, db_engine) VALUES (?,?,?,?)",
            ("ACME Corp", "@acme.com", "tenants/acme.sqlite3", "sqlite"))
conn.commit()
conn.close()
print("master DB created and sample client added.")
