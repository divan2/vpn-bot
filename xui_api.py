import requests
import json
import uuid
import logging
import psutil
import urllib3
from datetime import datetime, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class XUIAPI:
    def __init__(self, panel_url, username, password, api_prefix=""):
        self.panel_url = panel_url.rstrip('/')
        self.api_prefix = api_prefix.strip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self._login()

    def _login(self):
        try:
            url = f"{self.panel_url}/{self.api_prefix}/login"
            data = {"username": self.username, "password": self.password}
            logger.info(f"Отправка запроса на логин: {url}")
            response = self.session.post(url, json=data, verify=False, timeout=10)
            response.raise_for_status()
            result = response.json()
            logger.debug(f"Куки после логина: {self.session.cookies.get_dict()}")
            if result.get("success"):
                logger.info("Успешный логин в X-UI")
                return True
            print(f"Ошибка логина: {result.get('msg', 'Неизвестная ошибка')}")
        except Exception as e:
            logger.exception(f"Ошибка при логине: {e}")
        return False

    def _request(self, method, endpoint, data=None, params=None):
        try:
            url = f"{self.panel_url}/{self.api_prefix}{endpoint}"
            logger.info(f"Отправка запроса: {method} {url}")
            headers = {
                "User-Agent": "Mozilla/5.0",
                "X-Requested-With": "XMLHttpRequest"
            }
            response = self.session.request(
                method, url,
                json=data,
                params=params,
                headers=headers,
                timeout=15,
                verify=False
            )
            if response.status_code == 401:
                logger.warning("401 Unauthorized. Попробуем перелогиниться...")
                if self._login():
                    return self._request(method, endpoint, data, params)
                return {"success": False, "msg": "Ошибка повторного логина"}

            return response.json()
        except json.JSONDecodeError:
            print(f"Ошибка парсинга JSON: {response.text}")
            return {"success": False, "msg": "Ошибка JSON"}
        except Exception as e:
            logger.exception(f"Ошибка запроса: {e}")
            return {"success": False, "msg": str(e)}

    def get_inbounds(self):
        result = self._request("GET", "/panel/api/inbounds/list")
        if result.get("success"):
            return result.get("obj", [])
        print("X-UI не вернул список inbound'ов")
        return []

    def create_inbound(self, data):
        return self._request("POST", "/panel/api/inbounds/add", data=data)

    def update_inbound(self, inbound_id, data):
        return self._request("POST", f"/panel/api/inbounds/update/{inbound_id}", data=data)

    def del_inbound(self, inbound_id):
        return self._request("POST", f"/panel/api/inbounds/del/{inbound_id}")

    def create_user(self, remark, traffic_gb=40, expire_days=30):
        client_id = str(uuid.uuid4())
        email = f"{remark}_{client_id[:8]}@vpn.com"

        expire_timestamp = int((datetime.now() + timedelta(days=expire_days)).timestamp() * 1000)

        inbounds = self.get_inbounds()
        if not inbounds:
            logger.error("Нет доступных inboundов для создания пользователя")
            return None

        base_inbound = inbounds[0]
        port = self.find_free_port()

        settings = base_inbound.get("settings", {})
        if isinstance(settings, str):
            settings = json.loads(settings)

        clients = []
        print(f"DEBUG: Будет создан клиент с email={email}, uuid={client_id}")

        clients.append({
            "id": client_id,
            "flow": "xtls-rprx-vision",
            "email": email,
            "limitIp": 0,
            "totalGB": traffic_gb,
            "expiryTime": expire_timestamp
        })

        settings["clients"] = clients
        base_inbound["settings"] = settings
        base_inbound["port"] = port
        base_inbound["expiryTime"] = expire_timestamp
        base_inbound.pop("id", None)
        base_inbound.pop("inbound_id", None)

        for field in ["settings", "streamSettings", "sniffing", "allocate"]:
            if field in base_inbound and isinstance(base_inbound[field], dict):
                base_inbound[field] = json.dumps(base_inbound[field])

        result = self.create_inbound(base_inbound)
        if result.get("success"):
            return client_id, port

        logger.error(f"Ошибка при создании пользователя: {result.get('msg', 'Неизвестная ошибка')}")
        return None

    def update_user(self, uuid, traffic_gb=None, expire_days=None):
        inbounds = self.get_inbounds()
        for inbound in inbounds:
            settings = inbound.get("settings", {})
            if isinstance(settings, str):
                settings = json.loads(settings)

            clients = settings.get("clients", [])
            for client in clients:
                if client.get("id") == uuid:
                    if traffic_gb is not None:
                        client["totalGB"] = traffic_gb
                    if expire_days is not None:
                        client["expiryTime"] = int(
                            (datetime.now() + timedelta(days=expire_days)).timestamp() * 1000
                        )
                    settings["clients"] = clients
                    inbound["settings"] = settings
                    inbound["expiryTime"] = client["expiryTime"]
                    update_data = {k: v for k, v in inbound.items() if k not in ["id", "inbound_id"]}
                    return self.update_inbound(inbound["id"], update_data).get("success", False)
        print(f"Пользователь {uuid} не найден")
        return False

    def delete_user(self, uuid):
        inbounds = self.get_inbounds()
        for inbound in inbounds:
            settings = inbound.get("settings", {})
            if isinstance(settings, str):
                settings = json.loads(settings)

            clients = settings.get("clients", [])
            for client in clients:
                if client.get("id") == uuid:
                    return self.del_inbound(inbound["id"]).get("success", False)
        print(f"UUID {uuid} не найден для удаления")
        return False

    def generate_config(self, uuid, port):
        return (
            f"vless://{uuid}@divan4ikbmstu.online:{port}?"
            f"encryption=none&flow=xtls-rprx-vision&security=tls&"
            f"sni=divan4ikbmstu.online&fp=chrome&"
            f"type=tcp&headerType=none#{uuid[:8]}"
        )

    def get_server_stats(self):
        try:
            cpu_percent = psutil.cpu_percent()
            ram = psutil.virtual_memory()
            inbounds = self.get_inbounds()
            total_up = sum(inb.get("up", 0) for inb in inbounds)
            total_down = sum(inb.get("down", 0) for inb in inbounds)
            return {
                "cpu": cpu_percent,
                "ram": ram.percent,
                "upload": total_up / (1024 ** 3),
                "download": total_down / (1024 ** 3),
                "connections": len(inbounds)
            }
        except Exception as e:
            print(f"Ошибка получения статистики сервера: {str(e)}")
            return {
                "cpu": 0, "ram": 0, "upload": 0, "download": 0, "connections": 0
            }

    def find_free_port(self, start=21000, end=30000):
        used_ports = {inb.get("port") for inb in self.get_inbounds()}
        for port in range(start, end):
            if port not in used_ports:
                return port
        raise RuntimeError("Свободный порт не найден")

    def check_connection(self):
        if not self._login():
            return "❌ Ошибка аутентификации"
        result = self._request("GET", "/panel/api/inbounds/list")
        if result.get("success"):
            return "✅ Соединение с X-UI установлено"
        return f"❌ Ошибка соединения: {result.get('msg', 'Неизвестная ошибка')}"
