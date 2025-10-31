# core/views_tenants.py
from django.shortcuts import render, redirect
import pymysql
from django.contrib import messages
import os

MASTER_DB = os.environ.get('MASTER_DB_NAME', 'master_db')
ADMIN_CONF = {
    'host': os.environ.get('MYSQL_ADMIN_HOST', '127.0.0.1'),
    'port': int(os.environ.get('MYSQL_ADMIN_PORT', 3306)),
    'user': os.environ.get('MYSQL_ADMIN_USER', 'root'),
    'password': os.environ.get('MYSQL_ADMIN_PWD', ''),
    'database': MASTER_DB
}

def new_tenant_view(request):
    if request.method == 'GET':
        return render(request, 'core/new_tenant.html')
    # POST
    client_name = request.POST.get('client_name','').strip()
    domain = request.POST.get('domain','').strip()
    db_name = request.POST.get('db_name','').strip()
    if not client_name or not domain or not db_name:
        messages.error(request, "All fields are required.")
        return redirect('new_tenant')
    # Insert into master_db.clients_master
    conn = pymysql.connect(**ADMIN_CONF, cursorclass=pymysql.cursors.DictCursor, autocommit=True)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO clients_master (client_name, domain_postfix, db_name, db_host, db_engine, db_port)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (client_name, '@'+domain, db_name, '127.0.0.1', 'mysql', 3306))
    cur.close()
    conn.close()
    messages.success(request, f"Tenant {client_name} added. Run initializer to provision it.")
    return redirect('new_tenant')
