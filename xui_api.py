import requests
import json
import uuid
import logging
import psutil
import urllib3
from datetime import datetime, timedelta

# Отключение предупреждений о неверифицированных SSL-запросах
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Настройка логгера
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class XUIAPI:
    def __init__(self, panel_url, username, password):
        self.panel_url = panel_url.rstrip('/')
        self.username = username
        self.password = password
        self.jwt_token = None
        self._login()

    def _login(self):
        try:
            url = f"{self.panel_url}/login"
            data = {"username": self.username, "password": self.password}

            logger.info(f"Отправка запроса на логин: {url}")
            response = requests.post(
                url,
                json=data,
                timeout=10,
                verify=False
            )

            if response.status_code != 200:
                logger.error(f"Ошибка логина: HTTP {response.status_code}")
                return False

            result = response.json()
            if result.get('success'):
                self.jwt_token = response.cookies.get('session')
                logger.info("Успешный логин в X-UI")
                return True

            logger.error(f"Ошибка логина: {result.get('msg', 'Неизвестная ошибка')}")
            return False
        except Exception as e:
            logger.error(f"Ошибка при логине: {str(e)}", exc_info=True)
            return False

    def _request(self, method, endpoint, data=None, params=None):
        """Универсальный метод для запросов к API"""
        try:
            url = f"{self.panel_url}{endpoint}"
            headers = {
                "Content-Type": "application/json",
                "Cookie": f"session={self.jwt_token}"
            }

            logger.info(f"Отправка запроса: {method} {url}")
            response = requests.request(
                method,
                url,
                json=data,
                params=params,
                headers=headers,
                timeout=15,
                verify=False
            )

            if response.status_code == 401:
                logger.warning("Токен истек, выполняем перелогин")
                if self._login():
                    return self._request(method, endpoint, data, params)
                return {'success': False, 'msg': 'Ошибка перелогина'}

            try:
                return response.json()
            except json.JSONDecodeError:
                logger.error(f"Ошибка парсинга JSON: {response.text}")
                return {'success': False, 'msg': 'Неверный JSON в ответе'}
        except Exception as e:
            logger.error(f"Ошибка запроса: {str(e)}", exc_info=True)
            return {'success': False, 'msg': str(e)}

    def get_inbounds(self):
        """Получить список всех inbounds"""
        result = self._request("GET", "/panel/api/inbounds/list")
        return result.get('obj', []) if result.get('success') else []

    def create_inbound(self, data):
        """Создать новый inbound"""
        return self._request("POST", "/panel/api/inbounds/add", data=data)

    def update_inbound(self, inbound_id, data):
        """Обновить существующий inbound"""
        return self._request(
            "POST",
            f"/panel/api/inbounds/update/{inbound_id}",
            data=data
        )

    def del_inbound(self, inbound_id):
        """Удалить inbound"""
        return self._request(
            "POST",
            f"/panel/api/inbounds/del/{inbound_id}"
        )

    def create_user(self, remark, traffic_gb=40, expire_days=30):
        """Создать нового пользователя"""
        client_id = str(uuid.uuid4())
        expire_timestamp = int((datetime.now() + timedelta(days=expire_days)).timestamp() * 1000)

        data = {
            "up": 0,
            "down": 0,
            "total": traffic_gb * 1073741824,  # 1 GB = 1073741824 bytes
            "remark": remark,
            "enable": True,
            "expiryTime": expire_timestamp,
            "listen": "",
            "port": 443,  # Обязательный параметр
            "protocol": "vless",
            "settings": {
                "clients": [{
                    "id": client_id,
                    "flow": "xtls-rprx-vision",
                    "email": f"{remark}@vpn.com",
                    "limitIp": 0,
                    "totalGB": traffic_gb,
                    "expiryTime": expire_timestamp
                }],
                "decryption": "none"
            },
            "streamSettings": {
                "network": "tcp",
                "security": "tls",
                "tlsSettings": {
                    "serverName": "divan4ikbmstu.online",
                    "certificates": [{
                        "certificateFile": "/etc/letsencrypt/live/divan4ikbmstu.online/fullchain.pem",
                        "keyFile": "/etc/letsencrypt/live/divan4ikbmstu.online/privkey.pem"
                    }]
                }
            },
            "sniffing": {
                "enabled": True,
                "destOverride": ["http", "tls"]
            }
        }

        result = self.create_inbound(data)
        if result and result.get('success'):
            return client_id

        logger.error(f"Ошибка при создании пользователя: {result.get('msg', 'Неизвестная ошибка')}")
        return None

    def update_user(self, uuid, traffic_gb=None, expire_days=None):
        """Обновить пользователя"""
        inbounds = self.get_inbounds()
        for inbound in inbounds:
            clients = inbound.get('settings', {}).get('clients', [])
            for client in clients:
                if client.get('id') == uuid:
                    # Нашли нужного пользователя
                    inbound_id = inbound['id']

                    # Обновляем трафик
                    if traffic_gb is not None:
                        inbound["total"] = traffic_gb * 1073741824
                        for c in clients:
                            if c['id'] == uuid:
                                c['totalGB'] = traffic_gb

                    # Обновляем срок действия
                    if expire_days is not None:
                        expire_timestamp = int((datetime.now() + timedelta(days=expire_days)).timestamp() * 1000)
                        inbound["expiryTime"] = expire_timestamp
                        for c in clients:
                            if c['id'] == uuid:
                                c['expiryTime'] = expire_timestamp

                    # Обновляем клиентов
                    inbound["settings"]["clients"] = clients

                    # Удаляем лишние поля перед отправкой
                    update_data = {k: v for k, v in inbound.items() if k not in ['id', 'inbound_id']}

                    result = self.update_inbound(inbound_id, update_data)
                    if result and result.get('success'):
                        return True
                    return False

        logger.error(f"Пользователь для обновления не найден: {uuid}")
        return False

    def delete_user(self, uuid):
        """Удалить пользователя по UUID"""
        inbounds = self.get_inbounds()
        for inbound in inbounds:
            clients = inbound.get('settings', {}).get('clients', [])
            for client in clients:
                if client.get('id') == uuid:
                    result = self.del_inbound(inbound['id'])
                    if result and result.get('success'):
                        return True
                    return False

        logger.error(f"Пользователь для удаления не найден: {uuid}")
        return False

    def generate_config(self, uuid):
        return (
            f"vless://{uuid}@divan4ikbmstu.online:443?"
            f"encryption=none&flow=xtls-rprx-vision&security=tls&"
            f"sni=divan4ikbmstu.online&fp=chrome&"
            f"type=tcp&headerType=none#{uuid[:8]}"
        )

    def get_server_stats(self):
        """Получить статистику сервера"""
        try:
            # Получаем системную статистику
            cpu_percent = psutil.cpu_percent()
            ram = psutil.virtual_memory()

            # Получаем статистику трафика из X-UI
            inbounds = self.get_inbounds()
            total_up = 0
            total_down = 0

            for inbound in inbounds:
                total_up += inbound.get('up', 0)
                total_down += inbound.get('down', 0)

            return {
                'cpu': cpu_percent,
                'ram': ram.percent,
                'upload': total_up / (1024 ** 3),
                'download': total_down / (1024 ** 3),
                'connections': len(inbounds)
            }
        except Exception as e:
            logger.error(f"Ошибка получения статистики сервера: {str(e)}", exc_info=True)
            return {
                'cpu': 0,
                'ram': 0,
                'upload': 0,
                'download': 0,
                'connections': 0
            }

    def check_connection(self):
        """Проверка соединения с X-UI"""
        if not self._login():
            return "❌ Ошибка аутентификации в X-UI"

        result = self._request("GET", "/panel/api/inbounds/list")
        if result.get('success'):
            return "✅ Соединение с X-UI установлено"
        return f"❌ Ошибка соединения: {result.get('msg', 'Неизвестная ошибка')}"