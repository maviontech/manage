# core/management/commands/assign_admin_role.py
"""
Management command to assign Admin role to a user.
Usage: python manage.py assign_admin_role <member_email>
"""
from django.core.management.base import BaseCommand
import pymysql
import os


class Command(BaseCommand):
    help = 'Assign Admin role to a member'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='Email of the member to make admin')
        parser.add_argument('--tenant-db', type=str, help='Tenant database name (optional)')

    def handle(self, *args, **options):
        email = options['email']
        tenant_db = options.get('tenant_db')
        
        # Get database connection details from Django settings (fallback: env)
        from django.conf import settings
        def _cfg(name, default):
            v = getattr(settings, name, None)
            if v in (None, ''):
                v = os.environ.get(name)
            return v if v not in (None, '') else default
        host = _cfg('MYSQL_ADMIN_HOST', '127.0.0.1')
        port = int(_cfg('MYSQL_ADMIN_PORT', 3306))
        user = _cfg('MYSQL_ADMIN_USER', 'root')
        password = _cfg('MYSQL_ADMIN_PWD', 'root')
        master_db = _cfg('MASTER_DB_NAME', 'master_db')
        
        try:
            # Connect to master database
            conn = pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=master_db,
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True
            )
            cur = conn.cursor()
            
            # If tenant_db not provided, try to find it from email domain
            if not tenant_db:
                domain = email.split('@')[1] if '@' in email else None
                if domain:
                    cur.execute(
                        "SELECT db_name, db_user, db_password FROM clients_master WHERE domain_postfix = %s",
                        ('@' + domain,)
                    )
                    tenant = cur.fetchone()
                    if tenant:
                        tenant_db = tenant['db_name']
                        tenant_user = tenant['db_user']
                        tenant_pwd = tenant['db_password']
                    else:
                        self.stdout.write(self.style.ERROR(f'No tenant found for domain: {domain}'))
                        return
                else:
                    self.stdout.write(self.style.ERROR('Invalid email format'))
                    return
            else:
                # Get tenant credentials
                cur.execute(
                    "SELECT db_user, db_password FROM clients_master WHERE db_name = %s",
                    (tenant_db,)
                )
                tenant = cur.fetchone()
                if not tenant:
                    self.stdout.write(self.style.ERROR(f'Tenant database not found: {tenant_db}'))
                    return
                tenant_user = tenant['db_user']
                tenant_pwd = tenant['db_password']
            
            cur.close()
            conn.close()
            
            # Connect to tenant database
            tenant_conn = pymysql.connect(
                host=host,
                port=port,
                user=tenant_user,
                password=tenant_pwd,
                database=tenant_db,
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True
            )
            tenant_cur = tenant_conn.cursor()
            
            # Find member by email
            tenant_cur.execute("SELECT id FROM members WHERE email = %s", (email,))
            member = tenant_cur.fetchone()
            
            if not member:
                self.stdout.write(self.style.ERROR(f'Member not found: {email}'))
                return
            
            member_id = member['id']
            
            # Find Admin role
            tenant_cur.execute("SELECT id FROM roles WHERE name = 'Admin'")
            admin_role = tenant_cur.fetchone()
            
            if not admin_role:
                self.stdout.write(self.style.ERROR('Admin role not found in database'))
                return
            
            role_id = admin_role['id']
            
            # Assign Admin role (tenant-wide)
            tenant_cur.execute("""
                INSERT IGNORE INTO tenant_role_assignments (member_id, role_id, assigned_by)
                VALUES (%s, %s, %s)
            """, (member_id, role_id, member_id))
            
            if tenant_cur.rowcount > 0:
                self.stdout.write(self.style.SUCCESS(
                    f'Successfully assigned Admin role to {email} in {tenant_db}'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'{email} already has Admin role in {tenant_db}'
                ))
            
            tenant_cur.close()
            tenant_conn.close()
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
