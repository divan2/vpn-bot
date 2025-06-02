import requests
import json
import uuid
import os


class XUIAPI:
    def __init__(self, panel_url, username, password):
        self.panel_url = panel_url
        self.username = username
        self.password = password
        self.cookies = self._login()

    def _login(self):
        try:
            response = requests.post(
                f"{self.panel_url}/login",
                data={"username": self.username, "password": self.password},
                timeout=10
            )
            return response.cookies if response.status_code == 200 else None
        except Exception as e:
            print(f"Ошибка авторизации: {e}")
            return None

    def create_user(self, remark, traffic_gb=40, expire_days=30):
        client_id = str(uuid.uuid4())
        data = {
            "up": 0,
            "down": 0,
            "total": traffic_gb * 1024 ** 3,
            "remark": remark,
            "enable": True,
            "expiryTime": expire_days * 86400,
            "protocol": "vless",
            "settings": json.dumps({
                "clients": [{"id": client_id, "flow": "xtls-rprx-vision"}],
                "decryption": "none"
            }),
            "streamSettings": json.dumps({
                "network": "tcp",
                "security": "reality",
                "realitySettings": {
                    "dest": "www.microsoft.com:443",
                    "xver": 0,
                    "serverNames": ["your-domain.com"],
                    "privateKey": "your-private-key",
                    "shortIds": ["your-short-id"]
                }
            }),
            "sniffing": '{"enabled":true,"destOverride":["http","tls"]}'
        }

        try:
            response = requests.post(
                f"{self.panel_url}/xui/inbound/add",
                data=data,
                cookies=self.cookies,
                timeout=15
            )
            return client_id if response.status_code == 200 else None
        except Exception as e:
            print(f"Ошибка создания пользователя: {e}")
            return None

    def update_user(self, uuid, traffic_gb=None, expire_days=None):
        # В реальной реализации нужно получить текущие настройки и обновить
        print(f"Обновление пользователя {uuid}: traffic={traffic_gb}GB, days={expire_days}")
        return True

    def generate_config(self, uuid):
        return (
            f"vless://{uuid}@your-server.com:443?"
            "encryption=none&flow=xtls-rprx-vision&security=reality&"
            "sni=your-domain.com&fp=chrome&"
            "pbk=your-public-key&sid=your-short-id&"
            "type=tcp&headerType=none#MyVPN"
        )

    def get_server_stats(self):
        # Заглушка для статистики сервера
        return {
            'cpu': 15.7,
            'ram': 34.2,
            'upload': 24.8,
            'download': 56.3
        }