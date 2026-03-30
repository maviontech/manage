from django.conf import settings
from django.core.management.base import BaseCommand
import pymysql
import os

from chat.crypto import encrypt_chat_text, is_encrypted_chat_text


class Command(BaseCommand):
    help = "Encrypt existing plaintext chat history across all tenant databases."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many rows would be encrypted without modifying the database.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        master_conn = pymysql.connect(
            host=getattr(settings, "MYSQL_ADMIN_HOST", "127.0.0.1"),
            port=int(getattr(settings, "MYSQL_ADMIN_PORT", 3306)),
            user=getattr(settings, "MYSQL_ADMIN_USER", "root"),
            password=getattr(settings, "MYSQL_ADMIN_PWD", "root"),
            database=os.environ.get("MASTER_DB_NAME", "master_db"),
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=not dry_run,
        )

        total_dm = 0
        total_group = 0
        try:
            with master_conn.cursor() as cur:
                cur.execute("""
                    SELECT db_name, db_host, db_user, db_password
                    FROM clients_master
                """)
                tenants = cur.fetchall()
        finally:
            master_conn.close()

        for tenant in tenants:
            conn = pymysql.connect(
                host=tenant["db_host"],
                port=3306,
                user=tenant["db_user"],
                password=tenant["db_password"],
                database=tenant["db_name"],
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=not dry_run,
            )
            try:
                dm_count, group_count = self._encrypt_tenant(conn)
                if dry_run:
                    conn.rollback()
                total_dm += dm_count
                total_group += group_count
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{tenant['db_name']}: direct={dm_count}, group={group_count}"
                    )
                )
            finally:
                conn.close()

        self.stdout.write(
            self.style.SUCCESS(
                f"Completed chat encryption backfill. direct={total_dm}, group={total_group}"
            )
        )

    def _encrypt_tenant(self, conn):
        return (
            self._encrypt_table(conn, "chat_message"),
            self._encrypt_table(conn, "chat_group_message"),
        )

    def _encrypt_table(self, conn, table_name):
        updated = 0
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES LIKE %s", [table_name])
            if not cur.fetchone():
                return 0

            cur.execute(f"SELECT id, text FROM {table_name}")
            for row in cur.fetchall():
                text = row.get("text")
                if text is None or is_encrypted_chat_text(text):
                    continue
                cur.execute(
                    f"UPDATE {table_name} SET text=%s WHERE id=%s",
                    [encrypt_chat_text(text), row["id"]],
                )
                updated += 1
        return updated
