import mysql.connector
from mysql.connector import pooling

# Create a connection pool
connection_pool = pooling.MySQLConnectionPool(
    pool_name="face_attendance_pool",
    pool_size=5,
    host='localhost',
    user="root",
    password="Ni@9866IT",
    database="face_attendance",
    autocommit=True  # Enable autocommit to avoid lock issues
)

def get_db_connection():
    return connection_pool.get_connection()
