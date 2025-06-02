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
            "protocol": "vless",  # Или "vmess"
            "settings": json.dumps({
                "clients": [{
                    "id": client_id,
                    "flow": "xtls-rprx-vision"  # Только для VLESS
                }],
                "decryption": "none"
            }),
            "streamSettings": json.dumps({
                "network": "tcp",
                "security": "tls",  # Используем TLS вместо Reality
                "tlsSettings": {
                    "serverName": "divan4ikbmstu.online",
                    "certificates": [{
                        "certificateFile": "/etc/letsencrypt/live/divan4ikbmstu.online/fullchain.pem",
                        "keyFile": "/etc/letsencrypt/live/divan4ikbmstu.online/privkey.pem"
                    }]
                }
            }),
            "sniffing": '{"enabled":true,"destOverride":["http","tls"]}'
        }
        response = requests.post(
            f"{self.panel_url}/xui/inbound/add",
            data=data,
            cookies=self.cookies
        )
        return client_id if response.status_code == 200 else None

    def update_user(self, uuid, traffic_gb=None, expire_days=None):
        # В реальной реализации нужно получить текущие настройки и обновить
        print(f"Обновление пользователя {uuid}: traffic={traffic_gb}GB, days={expire_days}")
        return True

    def generate_config(self, uuid):
        return (
            f"vless://{uuid}@divan4ikbmstu.online:443?"
            f"encryption=none&flow=xtls-rprx-vision&security=tls&"
            f"sni=divan4ikbmstu.online&fp=chrome&"
            f"type=tcp&headerType=none#MyVPN"
        )

    def get_server_stats(self):
        # Заглушка для статистики сервера
        return {
            'cpu': 15.7,
            'ram': 34.2,
            'upload': 24.8,
            'download': 56.3
        }

    def check_connection(self):
        """Проверка работоспособности VPN"""
        try:
            # Проверка открытых портов
            port_check = os.system("nc -zv localhost 443 > /dev/null 2>&1")
            if port_check != 0:
                return "Порт 443 не открыт"

            # Проверка сертификата
            cert_check = os.system(
                f"openssl s_client -connect localhost:443 -servername {self.domain} < /dev/null 2>&1 | openssl x509 -noout -dates")
            if "notBefore" not in cert_check:
                return "Ошибка сертификата"

            # Проверка маршрутизации
            route_check = os.popen("sysctl net.ipv4.ip_forward").read().strip()
            if "net.ipv4.ip_forward = 1" not in route_check:
                return "IP forwarding отключен"

            return "Все проверки пройдены успешно"

        except Exception as e:
            return f"Ошибка проверки: {str(e)}"