import requests
import json
import uuid
import logging
import psutil
from datetime import datetime, timedelta

# Настройка логгера
logger = logging.getLogger(__name__)


class XUIAPI:
    def __init__(self, panel_url, username, password):
        self.panel_url = panel_url.rstrip('/')
        self.username = username
        self.password = password
        self.cookies = None
        self.jwt_token = None
        self._login()

    def _login(self):
        try:
            url = f"{self.panel_url}/login"
            data = {"username": self.username, "password": self.password}
            response = requests.post(
                url,
                json=data,
                timeout=10,
                verify=False
            )

            # Проверка на пустой ответ
            if not response.text.strip():
                logger.error("Login error: Empty response from server")
                return False

            try:
                result = response.json()
                if response.status_code == 200 and result.get('success'):
                    self.cookies = response.cookies
                    self.jwt_token = result.get('token', '')
                    return True
                logger.error(f"Login failed: {result.get('msg', 'Unknown error')}")
                return False
            except json.JSONDecodeError:
                logger.error(f"Login JSON parse error: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return False

    def _request(self, method, endpoint, data=None, params=None):
        """Универсальный метод для запросов к API"""
        try:
            url = f"{self.panel_url}{endpoint}"
            headers = {}
            if self.jwt_token:
                headers["Authorization"] = f"Bearer {self.jwt_token}"

            response = method(
                url,
                json=data,
                params=params,
                cookies=self.cookies,
                headers=headers,
                timeout=15,
                verify=False
            )

            # Проверка на пустой ответ
            if not response.text.strip():
                return {'success': True, 'msg': 'Empty response'}

            try:
                return response.json()
            except json.JSONDecodeError:
                logger.error(f"JSON parse error for {url}: {response.text}")
                return {'success': False, 'msg': 'Invalid JSON response'}
        except Exception as e:
            logger.error(f"Request error: {str(e)}")
            return {'success': False, 'msg': str(e)}

    def get_inbounds(self):
        """Получить список всех inbounds"""
        result = self._request(requests.get, "/xui/inbound/list")
        return result.get('obj', []) if result.get('success') else []

    def create_inbound(self, data):
        """Создать новый inbound"""
        result = self._request(requests.post, "/xui/inbound/add", data=data)
        return result.get('success', False)

    def update_inbound(self, inbound_id, data):
        """Обновить существующий inbound"""
        result = self._request(
            requests.post,
            f"/xui/inbound/update/{inbound_id}",
            data=data
        )
        return result.get('success', False)

    def del_inbound(self, inbound_id):
        """Удалить inbound"""
        result = self._request(
            requests.post,
            f"/xui/inbound/del/{inbound_id}"
        )
        return result.get('success', False)

    def create_user(self, remark, traffic_gb=40, expire_days=30):
        """Создать нового пользователя"""
        client_id = str(uuid.uuid4())
        expire_timestamp = int((datetime.now() + timedelta(days=expire_days)).timestamp() * 1000

        data = {
            "up": 0,
            "down": 0,
            "total": traffic_gb * 1073741824,  # 1 GB = 1073741824 bytes
            "remark": remark,
            "enable": True,
            "expiryTime": expire_timestamp,
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

        if self.create_inbound(data):
            return client_id
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

                    # Копируем текущие данные
                    update_data = inbound.copy()

                    # Удаляем ненужные поля
                    for field in ['id', 'inbound_id', 'streamSettings', 'sniffing']:
                        update_data.pop(field, None)

                    # Обновляем трафик
                    if traffic_gb is not None:
                        update_data["total"] = traffic_gb * 1073741824
                        for c in clients:
                            if c['id'] == uuid:
                                c['totalGB'] = traffic_gb

                    # Обновляем срок действия
                    if expire_days is not None:
                        expire_timestamp = int((datetime.now() + timedelta(days=expire_days)).timestamp() * 1000
                        update_data["expiryTime"] = expire_timestamp
                        for c in clients:
                            if
                        c['id'] == uuid:
                        c['expiryTime'] = expire_timestamp

                        # Обновляем клиентов
                        update_data["settings"]["clients"] = clients

                    return self.update_inbound(inbound_id, update_data)
        return False

    def delete_user(self, uuid):
        """Удалить пользователя по UUID"""
        inbounds = self.get_inbounds()
        for inbound in inbounds:
            clients = inbound.get('settings', {}).get('clients', [])
            for client in clients:
                if client.get('id') == uuid:
                    return self.del_inbound(inbound['id'])
        return False

    def generate_config(self, uuid):
        return (
            f"vless://{uuid}@divan4ikbmstu.online:443?"
            f"encryption=none&flow=xtls-rprx-vision&security=tls&"
            f"sni=divan4ikbmstu.online&fp=chrome&"
            f"type=tcp&headerType=none#MyVPN"
        )

    def get_server_stats(self):
        """Получить статистику сервера"""
        try:
            # Получаем системную статистику
            cpu_percent = psutil.cpu_percent()
            ram = psutil.virtual_memory()
            net = psutil.net_io_counters()

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
            logger.error(f"Server stats error: {str(e)}")
            return {
                'cpu': 0,
                'ram': 0,
                'upload': 0,
                'download': 0,
                'connections': 0
            }

    def check_connection(self):
        """Проверка соединения с X-UI"""
        return self._login() and len(self.get_inbounds()) >= 0