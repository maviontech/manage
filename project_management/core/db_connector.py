# db_connector.py
import pymysql
from typing import Dict, Any

def get_connection_from_config(config: Dict[str, Any]):
    """
    Connect using a config dict:
    {
      'db_engine': 'mysql',
      'db_name': 'tenant_acme',
      'db_host': '127.0.0.1',
      'db_port': 3306,
      'db_user': 'tenant_1',
      'db_password': '...'
    }
    """
    engine = config.get('db_engine', 'mysql')
    if engine != 'mysql':
        raise ValueError("Only MySQL is supported in this setup")

    conn = pymysql.connect(
        host=config.get('db_host', '127.0.0.1'),
        port=int(config.get('db_port', 3306)),
        user=config.get('db_user'),
        password=config.get('db_password'),
        database=config.get('db_name'),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )
    return conn
