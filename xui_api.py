import requests
import json
import uuid
import logging
import psutil
from datetime import datetime, timedelta  # Добавлен импорт timedelta

# Настройка логгера
logger = logging.getLogger(__name__)


class XUIAPI:
    def __init__(self, panel_url, username, password):
        self.panel_url = panel_url.rstrip('/')
        self.username = username
        self.password = password
        self.cookies = None
        self._login()

    def _login(self):
        try:
            response = requests.post(
                f"{self.panel_url}/login",
                data={"username": self.username, "password": self.password},
                timeout=10
            )
            if response.status_code == 200:
                self.cookies = response.cookies
                logger.info("Успешная авторизация в X-UI")
                return True
            logger.error("Ошибка авторизации: %s", response.text)
            return False
        except Exception as e:
            logger.error("Ошибка подключения к X-UI: %s", str(e))
            return False

    def get_inbounds(self):
        """Получить список всех inbounds"""
        if not self.cookies:
            if not self._login():
                return []

        try:
            response = requests.get(
                f"{self.panel_url}/xui/inbound/list",
                cookies=self.cookies,
                timeout=10
            )
            if response.status_code == 200:
                return response.json().get('data', [])
            logger.error("Ошибка получения inbounds: %s", response.text)
            return []
        except Exception as e:
            logger.error("Ошибка получения inbounds: %s", str(e))
            return []

    def create_inbound(self, data):
        """Создать новый inbound"""
        if not self.cookies:
            if not self._login():
                return False

        try:
            response = requests.post(
                f"{self.panel_url}/xui/inbound/add",
                data=data,
                cookies=self.cookies,
                timeout=15
            )
            if response.status_code == 200:
                logger.info("Inbound успешно создан")
                return True
            logger.error("Ошибка создания inbound: %s", response.text)
            return False
        except Exception as e:
            logger.error("Ошибка создания inbound: %s", str(e))
            return False

    def update_inbound(self, inbound_id, data):
        """Обновить существующий inbound"""
        if not self.cookies:
            if not self._login():
                return False

        try:
            response = requests.post(
                f"{self.panel_url}/xui/inbound/update/{inbound_id}",
                data=data,
                cookies=self.cookies,
                timeout=15
            )
            if response.status_code == 200:
                logger.info("Inbound успешно обновлен")
                return True
            logger.error("Ошибка обновления inbound: %s", response.text)
            return False
        except Exception as e:
            logger.error("Ошибка обновления inbound: %s", str(e))
            return False

    def create_user(self, remark, traffic_gb=40, expire_days=30):
        """Создать нового пользователя"""
        client_id = str(uuid.uuid4())
        expire_timestamp = int((datetime.now() + timedelta(days=expire_days)).timestamp()) * 1000

        data = {
            "up": 0,
            "down": 0,
            "total": traffic_gb * 1073741824,  # 1 GB = 1073741824 bytes
            "remark": remark,
            "enable": True,
            "expiryTime": expire_timestamp,
            "protocol": "vless",
            "settings": json.dumps({
                "clients": [{
                    "id": client_id,
                    "flow": "xtls-rprx-vision",
                    "email": f"{remark}@vpn.com",
                    "limitIp": 0,
                    "totalGB": traffic_gb,
                    "expiryTime": expire_timestamp
                }],
                "decryption": "none"
            }),
            "streamSettings": json.dumps({
                "network": "tcp",
                "security": "tls",
                "tlsSettings": {
                    "serverName": "divan4ikbmstu.online",
                    "certificates": [{
                        "certificateFile": "/etc/letsencrypt/live/divan4ikbmstu.online/fullchain.pem",
                        "keyFile": "/etc/letsencrypt/live/divan4ikbmstu.online/privkey.pem"
                    }]
                }
            }),
            "sniffing": json.dumps({
                "enabled": True,
                "destOverride": ["http", "tls"]
            })
        }

        if self.create_inbound(data):
            return client_id
        return None

    def update_user(self, uuid, traffic_gb=None, expire_days=None):
        """Обновить пользователя"""
        inbounds = self.get_inbounds()
        for inbound in inbounds:
            settings = json.loads(inbound.get('settings', '{}'))
            clients = settings.get('clients', [])
            for client in clients:
                if client.get('id') == uuid:
                    # Нашли нужного пользователя
                    inbound_id = inbound['id']

                    # Обновляем параметры
                    update_data = {
                        "id": inbound_id,
                        "up": inbound['up'],
                        "down": inbound['down'],
                        "remark": inbound['remark'],
                        "enable": inbound['enable'],
                        "protocol": inbound['protocol'],
                        "settings": inbound['settings'],
                        "streamSettings": inbound['streamSettings'],
                        "sniffing": inbound['sniffing']
                    }

                    # Обновляем трафик
                    if traffic_gb is not None:
                        update_data["total"] = traffic_gb * 1073741824
                        # Обновляем лимит в клиенте
                        for client in clients:
                            if client['id'] == uuid:
                                client['totalGB'] = traffic_gb
                        update_data["settings"] = json.dumps({
                            "clients": clients,
                            "decryption": "none"
                        })

                    # Обновляем срок действия
                    if expire_days is not None:
                        expire_timestamp = int((datetime.now() + timedelta(days=expire_days)).timestamp()) * 1000
                        update_data["expiryTime"] = expire_timestamp
                        # Обновляем срок в клиенте
                        for client in clients:
                            if client['id'] == uuid:
                                client['expiryTime'] = expire_timestamp
                        update_data["settings"] = json.dumps({
                            "clients": clients,
                            "decryption": "none"
                        })

                    return self.update_inbound(inbound_id, update_data)

        logger.error("Пользователь с UUID %s не найден", uuid)
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

            return {
                'cpu': cpu_percent,
                'ram': ram.percent,
                'upload': net.bytes_sent / (1024 ** 3),
                'download': net.bytes_recv / (1024 ** 3),
                'connections': len(self.get_inbounds())  # Простой подсчёт
            }
        except Exception as e:
            logger.error("Ошибка получения статистики: %s", str(e))
            return {
                'cpu': 0,
                'ram': 0,
                'upload': 0,
                'download': 0,
                'connections': 0
            }