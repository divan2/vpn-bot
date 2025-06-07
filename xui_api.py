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
            logger.info(f"Попытка входа в X-UI панель: {url}")

            response = self.session.post(url, json=data, verify=False, timeout=10)
            response.raise_for_status()

            result = response.json()
            if result.get("success"):
                logger.info("Успешная аутентификация в X-UI")
                return True

            error_msg = result.get("msg", "Неизвестная ошибка")
            logger.error(f"Ошибка входа: {error_msg}")
            return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка сети при входе: {str(e)}")
        except json.JSONDecodeError:
            logger.error("Неверный JSON-ответ при входе")
        except Exception as e:
            logger.error(f"Неожиданная ошибка при входе: {str(e)}")
        return False

    def _request(self, method, endpoint, data=None, params=None):
        try:
            url = f"{self.panel_url}/{self.api_prefix}{endpoint}"
            logger.debug(f"Отправка запроса: {method} {url}")

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
                logger.warning("Требуется повторная аутентификация (401)")
                if self._login():
                    return self._request(method, endpoint, data, params)
                return {"success": False, "msg": "Ошибка повторного входа"}

            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка сети при запросе {endpoint}: {str(e)}")
            return {"success": False, "msg": str(e)}
        except json.JSONDecodeError:
            logger.error(f"Не удалось декодировать JSON для {endpoint}")
            return {"success": False, "msg": "Invalid JSON response"}
        except Exception as e:
            logger.error(f"Неожиданная ошибка при запросе {endpoint}: {str(e)}")
            return {"success": False, "msg": str(e)}

    def get_inbounds(self):
        result = self._request("GET", "/panel/api/inbounds/list")
        if result.get("success"):
            inbounds = result.get("obj", [])
            logger.debug(f"Получено {len(inbounds)} inbounds")
            return inbounds

        logger.error(f"Ошибка получения inbounds: {result.get('msg', 'Неизвестная ошибка')}")
        return []

    def create_inbound(self, data):
        result = self._request("POST", "/panel/api/inbounds/add", data=data)
        if result.get("success"):
            logger.info(f"Создан новый inbound: {data.get('remark', 'Без названия')}")
        else:
            logger.error(f"Ошибка создания inbound: {result.get('msg', 'Неизвестная ошибка')}")
        return result

    def update_inbound(self, inbound_id, data):
        result = self._request("POST", f"/panel/api/inbounds/update/{inbound_id}", data=data)
        if result.get("success"):
            logger.info(f"Обновлен inbound {inbound_id}")
        else:
            logger.error(f"Ошибка обновления inbound {inbound_id}: {result.get('msg', 'Неизвестная ошибка')}")
        return result

    def del_inbound(self, inbound_id):
        result = self._request("POST", f"/panel/api/inbounds/del/{inbound_id}")
        if result.get("success"):
            logger.info(f"Удален inbound {inbound_id}")
        else:
            logger.error(f"Ошибка удаления inbound {inbound_id}: {result.get('msg', 'Неизвестная ошибка')}")
        return result

    def create_user(self, remark, traffic_gb=40, expire_days=30):
        try:
            client_id = str(uuid.uuid4())
            email = f"{remark}_{client_id[:8]}@vpn.com"
            logger.info(f"Создание пользователя: {remark}, трафик: {traffic_gb}GB, срок: {expire_days} дней")

            expire_timestamp = int((datetime.now() + timedelta(days=expire_days)).timestamp() * 1000)
            inbounds = self.get_inbounds()

            if not inbounds:
                logger.error("Нет доступных inbounds для создания пользователя")
                return None

            base_inbound = inbounds[0]
            port = self.find_free_port()

            settings = base_inbound.get("settings", {})
            if isinstance(settings, str):
                try:
                    settings = json.loads(settings)
                except json.JSONDecodeError:
                    logger.error("Не удалось декодировать настройки inbound")
                    return None

            clients = settings.get("clients", [])
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
                logger.info(f"Пользователь успешно создан: {client_id}, порт: {port}")
                return client_id, port

            logger.error(f"Ошибка создания пользователя: {result.get('msg', 'Неизвестная ошибка')}")
            return None

        except Exception as e:
            logger.error(f"Неожиданная ошибка при создании пользователя: {str(e)}")
            return None

    def update_user(self, uuid, traffic_gb=None, expire_days=None):
        try:
            logger.info(f"Обновление пользователя {uuid}: трафик={traffic_gb}GB, дней={expire_days}")

            inbounds = self.get_inbounds()
            for inbound in inbounds:
                settings = inbound.get("settings", {})
                if isinstance(settings, str):
                    settings = json.loads(settings)

                clients = settings.get("clients", [])
                for client in clients:
                    if client.get("id") == uuid:
                        updated = False

                        if traffic_gb is not None:
                            client["totalGB"] = traffic_gb
                            updated = True

                        if expire_days is not None:
                            new_expire = int((datetime.now() + timedelta(days=expire_days)).timestamp() * 1000)
                            client["expiryTime"] = new_expire
                            inbound["expiryTime"] = new_expire
                            updated = True

                        if not updated:
                            logger.warning("Нет изменений для обновления")
                            return False

                        settings["clients"] = clients
                        inbound["settings"] = settings
                        update_data = {k: v for k, v in inbound.items() if k not in ["id", "inbound_id"]}

                        result = self.update_inbound(inbound["id"], update_data)
                        return result.get("success", False)

            logger.warning(f"Пользователь {uuid} не найден для обновления")
            return False

        except Exception as e:
            logger.error(f"Неожиданная ошибка при обновлении пользователя {uuid}: {str(e)}")
            return False

    def delete_user(self, uuid):
        try:
            logger.info(f"Попытка удаления пользователя {uuid}")

            inbounds = self.get_inbounds()
            for inbound in inbounds:
                settings = inbound.get("settings", {})
                if isinstance(settings, str):
                    settings = json.loads(settings)

                clients = settings.get("clients", [])
                for client in clients:
                    if client.get("id") == uuid:
                        result = self.del_inbound(inbound["id"])
                        return result.get("success", False)

            logger.warning(f"Пользователь {uuid} не найден для удаления")
            return False

        except Exception as e:
            logger.error(f"Неожиданная ошибка при удалении пользователя {uuid}: {str(e)}")
            return False

    def generate_config(self, uuid, port):
        config = (
            f"vless://{uuid}@divan4ikbmstu.online:{port}?"
            f"encryption=none&flow=xtls-rprx-vision&security=tls&"
            f"sni=divan4ikbmstu.online&fp=chrome&"
            f"type=tcp&headerType=none#{uuid[:8]}"
        )
        logger.debug(f"Сгенерирована конфигурация для {uuid}")
        return config

    def get_server_stats(self):
        try:
            cpu_percent = psutil.cpu_percent()
            ram = psutil.virtual_memory()

            inbounds = self.get_inbounds()
            total_up = sum(inb.get("up", 0) for inb in inbounds)
            total_down = sum(inb.get("down", 0) for inb in inbounds)

            stats = {
                "cpu": cpu_percent,
                "ram": ram.percent,
                "upload": total_up / (1024 ** 3),
                "download": total_down / (1024 ** 3),
                "connections": len(inbounds)
            }

            logger.debug(f"Статистика сервера: {stats}")
            return stats

        except Exception as e:
            logger.error(f"Ошибка получения статистики сервера: {str(e)}")
            return {
                "cpu": 0, "ram": 0, "upload": 0, "download": 0, "connections": 0
            }

    def find_free_port(self, start=21000, end=30000):
        try:
            used_ports = {inb.get("port") for inb in self.get_inbounds()}
            for port in range(start, end):
                if port not in used_ports:
                    logger.debug(f"Найден свободный порт: {port}")
                    return port

            logger.error("Не найдено свободных портов в указанном диапазоне")
            raise RuntimeError("Свободный порт не найден")

        except Exception as e:
            logger.error(f"Ошибка поиска свободного порта: {str(e)}")
            raise

    def check_connection(self):
        if not self._login():
            logger.error("Проверка соединения: ошибка аутентификации")
            return "❌ Ошибка аутентификации"

        result = self._request("GET", "/panel/api/inbounds/list")
        if result.get("success"):
            logger.info("Проверка соединения: успешно")
            return "✅ Соединение с X-UI установлено"

        error_msg = result.get("msg", "Неизвестная ошибка")
        logger.error(f"Проверка соединения: ошибка - {error_msg}")
        return f"❌ Ошибка соединения: {error_msg}"