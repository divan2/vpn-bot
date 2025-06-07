import sqlite3
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_name='vpn_bot.db'):
        try:
            self.conn = sqlite3.connect(db_name)
            self.cursor = self.conn.cursor()
            self._create_tables()
            logger.info(f"База данных {db_name} успешно подключена")
        except sqlite3.Error as e:
            logger.critical(f"Ошибка подключения к базе данных: {str(e)}")
            raise

    def _create_tables(self):
        try:
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
            logger.debug("Таблицы успешно созданы/проверены")
        except sqlite3.Error as e:
            logger.error(f"Ошибка создания таблиц: {str(e)}")
            raise

    def user_exists(self, user_id):
        try:
            self.cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
            exists = self.cursor.fetchone() is not None
            logger.debug(f"Проверка существования пользователя {user_id}: {exists}")
            return exists
        except sqlite3.Error as e:
            logger.error(f"Ошибка проверки пользователя {user_id}: {str(e)}")
            return False

    def create_user(self, user_id, username, uuid, traffic_limit, expire_date):
        try:
            created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.cursor.execute('''
                INSERT INTO users (user_id, username, uuid, traffic_limit, expire_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, username, uuid, traffic_limit, expire_date, created_at))
            self.conn.commit()
            logger.info(f"Создан новый пользователь: {user_id}, UUID: {uuid}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка создания пользователя {user_id}: {str(e)}")
            return False

    def get_user(self, user_id):
        try:
            self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = self.cursor.fetchone()
            if row:
                user_data = {
                    'user_id': row[0],
                    'username': row[1],
                    'uuid': row[2],
                    'traffic_limit': row[3],
                    'traffic_used': row[4],
                    'expire_date': row[5],
                    'is_active': bool(row[6]),
                    'created_at': row[7]
                }
                logger.debug(f"Данные пользователя {user_id} получены")
                return user_data
            logger.warning(f"Пользователь {user_id} не найден")
            return None
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения данных пользователя {user_id}: {str(e)}")
            return None

    def get_all_users(self):
        try:
            self.cursor.execute("SELECT * FROM users")
            columns = [col[0] for col in self.cursor.description]
            users = [dict(zip(columns, row)) for row in self.cursor.fetchall()]
            logger.debug(f"Получено {len(users)} пользователей")
            return users
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения списка пользователей: {str(e)}")
            return []

    def update_user(self, user_id, **kwargs):
        try:
            if not kwargs:
                logger.warning("Нет данных для обновления")
                return False

            set_clause = ', '.join([f"{key} = ?" for key in kwargs])
            values = list(kwargs.values())
            values.append(user_id)

            query = f"UPDATE users SET {set_clause} WHERE user_id = ?"
            self.cursor.execute(query, values)
            self.conn.commit()

            success = self.cursor.rowcount > 0
            if success:
                logger.info(f"Пользователь {user_id} обновлен: {kwargs}")
            else:
                logger.warning(f"Пользователь {user_id} не найден для обновления")
            return success
        except sqlite3.Error as e:
            logger.error(f"Ошибка обновления пользователя {user_id}: {str(e)}")
            return False

    def delete_user(self, user_id):
        try:
            self.cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            self.conn.commit()
            success = self.cursor.rowcount > 0
            if success:
                logger.info(f"Пользователь {user_id} удален из БД")
            else:
                logger.warning(f"Пользователь {user_id} не найден в БД")
            return success
        except sqlite3.Error as e:
            logger.error(f"Ошибка удаления пользователя {user_id}: {str(e)}")
            return False

    def close(self):
        try:
            self.conn.close()
            logger.info("Соединение с базой данных закрыто")
        except sqlite3.Error as e:
            logger.error(f"Ошибка при закрытии соединения: {str(e)}")