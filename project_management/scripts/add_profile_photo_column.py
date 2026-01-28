"""
Script to add profile_photo column to the members table in all tenant databases.
Run this after adding the profile photo feature to update existing tenants.
"""

import os
import sys
import pymysql
import logging
logger = logging.getLogger('project_management')

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Get MySQL admin credentials from environment or use defaults
MASTER_DB = os.environ.get('MASTER_DB_NAME', 'master_db')
ADMIN_HOST = os.environ.get('MYSQL_ADMIN_HOST', '127.0.0.1')
ADMIN_PORT = int(os.environ.get('MYSQL_ADMIN_PORT', 3306))
ADMIN_USER = os.environ.get('MYSQL_ADMIN_USER', 'root')
ADMIN_PWD = os.environ.get('MYSQL_ADMIN_PWD', 'root')

def add_profile_photo_column():
    """Add profile_photo column to members table in all tenant databases"""
    
    try:
        # Connect to master database
        master_conn = pymysql.connect(
            host=ADMIN_HOST,
            port=ADMIN_PORT,
            user=ADMIN_USER,
            password=ADMIN_PWD,
            database=MASTER_DB,
            cursorclass=pymysql.cursors.DictCursor
        )
        
        if not master_conn:
            logger.error("❌ Failed to connect to master database")
            return
        
        master_cursor = master_conn.cursor()
        
        # Get all tenants
        master_cursor.execute("SELECT * FROM clients_master WHERE db_engine='mysql'")
        tenants = master_cursor.fetchall()
        
        if not tenants:
            logger.warning("⚠️  No tenants found in master database")
            master_cursor.close()
            master_conn.close()
            return
        
        logger.info(f"\n📋 Found {len(tenants)} tenant(s)")
        logger.info("=" * 60)
        
        success_count = 0
        error_count = 0
        
        for tenant in tenants:
            tenant_id = tenant.get('id')
            db_name = tenant.get('db_name')
            db_user = tenant.get('db_user')
            db_password = tenant.get('db_password')
            db_host = tenant.get('db_host', '127.0.0.1')
            db_port = tenant.get('db_port', 3306)
            
            if not all([db_name, db_user, db_password]):
                logger.warning(f"⚠️  Skipping tenant {tenant_id}: Missing database credentials")
                continue
            
            try:
                logger.info(f"\n🔧 Processing tenant: {tenant_id} (DB: {db_name})")
                
                # Connect to tenant database
                tenant_conn = pymysql.connect(
                    host=db_host,
                    port=db_port,
                    user=db_user,
                    password=db_password,
                    database=db_name,
                    charset='utf8mb4',
                    cursorclass=pymysql.cursors.DictCursor
                )
                
                tenant_cursor = tenant_conn.cursor()
                
                # Check if column already exists
                tenant_cursor.execute("""
                    SELECT COLUMN_NAME 
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_SCHEMA = %s 
                    AND TABLE_NAME = 'members' 
                    AND COLUMN_NAME = 'profile_photo'
                """, (db_name,))
                
                column_exists = tenant_cursor.fetchone()
                
                if column_exists:
                    logger.info(f"   ⏭️  Column 'profile_photo' already exists in members table")
                else:
                    # Add the profile_photo column
                    tenant_cursor.execute("""
                        ALTER TABLE members 
                        ADD COLUMN profile_photo VARCHAR(512) NULL 
                        COMMENT 'Path to profile photo file'
                    """)
                    tenant_conn.commit()
                    logger.info(f"   ✅ Added 'profile_photo' column to members table")
                
                tenant_cursor.close()
                tenant_conn.close()
                success_count += 1
                
            except Exception as e:
                logger.error(f"   ❌ Error processing tenant {tenant_id}: {str(e)}", exc_info=True)
                error_count += 1
                continue
        
        master_cursor.close()
        master_conn.close()
        
        logger.info("\n" + "=" * 60)
        logger.info(f"📊 Summary:")
        logger.info(f"   ✅ Success: {success_count}")
        logger.info(f"   ❌ Errors: {error_count}")
        logger.info("=" * 60 + "\n")
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}", exc_info=True)

if __name__ == "__main__":
    logger.info("\n" + "=" * 60)
    logger.info("🖼️  Adding profile_photo column to members table")
    logger.info("=" * 60)
    add_profile_photo_column()
