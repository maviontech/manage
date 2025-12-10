"""
List all tenant databases from master_db
"""

import pymysql

try:
    print("\n" + "="*60)
    print("TENANT DATABASES")
    print("="*60 + "\n")
    
    # Try direct connection
    conn = pymysql.connect(
        host='localhost',
        user='root',
        password='',
        database='master_db',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    
    cursor = conn.cursor()
    
    cursor.execute("SELECT tenant_id, db_name, client_name FROM tenants ORDER BY tenant_id")
    tenants = cursor.fetchall()
    
    if not tenants:
        print("⚠️  No tenants found in master database")
        print("\nAvailable databases:")
        cursor.execute("SHOW DATABASES")
        dbs = cursor.fetchall()
        for db in dbs:
            db_name = db['Database']
            if db_name not in ['information_schema', 'mysql', 'performance_schema', 'sys', 'master_db']:
                print(f"   • {db_name}")
    else:
        print(f"Found {len(tenants)} tenant(s):\n")
        for i, tenant in enumerate(tenants, 1):
            print(f"{i}. Tenant ID: {tenant['tenant_id']}")
            print(f"   Database: {tenant['db_name']}")
            print(f"   Client: {tenant.get('client_name', 'N/A')}")
            print()
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    print("\nTrying to list all databases...")
    
    try:
        conn = pymysql.connect(
            host='localhost',
            user='root',
            password='',
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        cursor = conn.cursor()
        cursor.execute("SHOW DATABASES")
        dbs = cursor.fetchall()
        print("\nAvailable databases:")
        for db in dbs:
            db_name = db['Database']
            if db_name not in ['information_schema', 'mysql', 'performance_schema', 'sys']:
                print(f"   • {db_name}")
        cursor.close()
        conn.close()
    except Exception as e2:
        print(f"❌ Error: {e2}")
