import sqlite3
from datetime import datetime


class Database:
    def __init__(self, db_name='vpn_bot.db'):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self._create_tables()

    def _create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                uuid TEXT,
                traffic_limit INTEGER,
                traffic_used INTEGER DEFAULT 0,
                expire_date TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT
            )
        ''')
        self.conn.commit()

    def user_exists(self, user_id):
        self.cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone() is not None

    def create_user(self, user_id, username, uuid, traffic_limit, expire_date):
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.cursor.execute('''
            INSERT INTO users (user_id, username, uuid, traffic_limit, expire_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, uuid, traffic_limit, expire_date, created_at))
        self.conn.commit()

    def get_user(self, user_id):
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = self.cursor.fetchone()
        if row:
            return {
                'user_id': row[0],
                'username': row[1],
                'uuid': row[2],
                'traffic_limit': row[3],
                'traffic_used': row[4],
                'expire_date': row[5],
                'is_active': bool(row[6]),
                'created_at': row[7]
            }
        return None

    def get_all_users(self):
        self.cursor.execute("SELECT * FROM users")
        columns = [col[0] for col in self.cursor.description]
        return [dict(zip(columns, row)) for row in self.cursor.fetchall()]

    def update_user(self, user_id, **kwargs):
        set_clause = ', '.join([f"{key} = ?" for key in kwargs])
        values = list(kwargs.values())
        values.append(user_id)

        self.cursor.execute(f'''
            UPDATE users SET {set_clause} WHERE user_id = ?
        ''', values)
        self.conn.commit()
        return self.cursor.rowcount > 0

    def delete_user(self, user_id):
        """Удалить пользователя"""
        print(f"Удаление пользователя из БД: {user_id}")
        self.cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        self.conn.commit()
        return self.cursor.rowcount > 0

    def close(self):
        self.conn.close()