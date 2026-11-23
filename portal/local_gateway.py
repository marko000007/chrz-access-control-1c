"""Loopback HTTP adapter: every business response is executed by the real 1C runtime."""
import base64
import binascii
from contextlib import contextmanager
import fcntl
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time
from urllib.parse import urlsplit
import uuid

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BINARY = Path("/Applications/1cv8t.localized/8.3.27.1606/1cv8t.app/Contents/MacOS/1cv8t")
CONFIG = ROOT/".local/local-erp.json"
ROUTES = {"GET": {"/health", "/actors/me", "/references", "/requests", "/passes", "/events"},
    "POST": {"/requests", "/requests/approve", "/requests/reject", "/requests/cancel", "/passes", "/passes/revoke", "/movements"}}


class LocalERPError(Exception):
    pass


class OneCRuntime:
    def __init__(self, base_name="development", root=ROOT, binary=None):
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", base_name):
            raise LocalERPError("Некорректное имя локальной базы.")
        self.root = Path(root).resolve()
        parent = self.root/".local/1c"
        self.base = (parent/base_name).resolve()
        if self.base.parent != parent.resolve() or not (self.base/"1Cv8.1CD").is_file():
            raise LocalERPError("Сначала соберите отдельную локальную базу 1С.")
        self.binary = Path(binary or os.getenv("ONE_C_BINARY", str(DEFAULT_BINARY)))
        if not self.binary.is_file():
            raise LocalERPError("Исполняемый файл 1С не найден.")
        self.directory = self.base/"local-rpc"
        self.directory.mkdir(mode=0o700, exist_ok=True)
        if self.directory.is_symlink():
            raise LocalERPError("Каталог обмена не должен быть ссылкой.")
        self.directory.chmod(0o700)
        self.lock = threading.Lock()

    @contextmanager
    def exclusive(self):
        if not self.lock.acquire(timeout=25):
            raise LocalERPError("Локальная 1С занята.")
        try:
            with (self.directory/"gateway.lock").open("a") as lockfile:
                deadline = time.monotonic()+25
                while True:
                    try:
                        fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise LocalERPError("Локальная 1С занята другим процессом.")
                        time.sleep(.05)
                try: yield
                finally: fcntl.flock(lockfile, fcntl.LOCK_UN)
        finally:
            self.lock.release()

    def invoke(self, payload):
        request_id = str(uuid.uuid4())
        encoded = json.dumps({**payload, "request_id": request_id}, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(encoded) > 270000:
            raise LocalERPError("Слишком большой локальный запрос.")
        with self.exclusive():
            request = self.directory/"request.json"
            response = self.directory/"response.json"
            response.unlink(missing_ok=True)
            temporary = self.directory/"request.pending"
            temporary.write_bytes(encoded); temporary.chmod(0o600); temporary.replace(request)
            try:
                result = subprocess.run([str(self.binary), "ENTERPRISE", "/F", str(self.base),
                    "/C", "local-rpc", "/DisableStartupMessages", "/DisableStartupDialogs",
                    "/Out", str(self.directory/"runtime.log")], cwd=self.binary.parent, capture_output=True, timeout=25)
                if result.returncode or not response.is_file() or response.stat().st_size > 1024*1024:
                    raise LocalERPError("Локальная 1С не подтвердила выполнение запроса.")
                data = json.loads(response.read_text(encoding="utf-8-sig"))
                if data.get("local_error"):
                    diagnostic = self.directory/"last-error.log"
                    diagnostic.write_text(str(data["local_error"])[:6000], encoding="utf-8")
                    diagnostic.chmod(0o600)
                if data.get("request_id") != request_id or type(data.get("status")) is not int or not 200 <= data["status"] <= 599 or not isinstance(data.get("result"), dict):
                    raise LocalERPError("Некорректный ответ локальной 1С.")
                return data["status"], data["result"]
            except (subprocess.TimeoutExpired, OSError, ValueError, AttributeError) as exc:
                raise LocalERPError("Выполнение не подтверждено; повторите ту же команду.") from exc
            finally:
                request.unlink(missing_ok=True); response.unlink(missing_ok=True)


def create_server(runtime, username, password, port=0):
    if not username or not password or ":" in username:
        raise LocalERPError("Укажите реквизиты локального адаптера.")
    authorization = "Basic "+base64.b64encode(f"{username}:{password}".encode()).decode("ascii")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, result):
            raw = json.dumps(result, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            try: self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError): pass

        def dispatch(self):
            try:
                self.connection.settimeout(30)
                host = self.headers.get("Host", "")
                allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
                if host not in allowed or self.headers.get("Origin"):
                    self.reply(403, {"error":"Источник запроса закрыт."}); return
                supplied = self.headers.get("Authorization", "")
                if not hmac.compare_digest(supplied.encode(), authorization.encode()):
                    self.reply(401, {"error":"Доступ закрыт."}); return
                parsed = urlsplit(self.path)
                detail = self.command == "GET" and re.fullmatch(r"/(?:requests|passes)/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", parsed.path)
                report = self.command == "GET" and re.fullmatch(r"/reports/movements/[0-9]{8}/[0-9]{8}", parsed.path)
                if parsed.query or parsed.fragment or (parsed.path not in ROUTES.get(self.command, set()) and not detail and not report):
                    self.reply(404, {"error":"Маршрут не найден."}); return
                actor = base64.b64decode(self.headers.get("X-Portal-Actor", ""), validate=True).decode("utf-8")
                if not actor or len(actor)>150 or any(ord(char)<32 for char in actor):
                    raise ValueError
                body, key = "", ""
                if self.command == "POST":
                    if self.headers.get("Transfer-Encoding") or self.headers.get_content_type() != "application/json":
                        raise ValueError
                    length = int(self.headers.get("Content-Length", "-1"))
                    if not 0 < length <= 128*1024: raise ValueError
                    key = str(uuid.UUID(self.headers.get("Idempotency-Key", "")))
                    raw = self.rfile.read(length)
                    if len(raw) != length: raise ValueError
                    body = raw.decode("utf-8")
                    if not isinstance(json.loads(body), dict): raise ValueError
                status, result = runtime.invoke({"method":self.command, "path":parsed.path, "actor":actor, "body":body, "key":key})
                self.reply(status, result)
            except (ValueError, UnicodeError, binascii.Error, TimeoutError):
                self.reply(400, {"error":"Некорректный запрос."})
            except LocalERPError:
                self.reply(503, {"error":"Локальная 1С временно недоступна; сохраните ключ команды для повтора."})

        do_GET = dispatch
        do_POST = dispatch

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def save_configuration(base_name, port=0):
    if CONFIG.exists():
        config = json.loads(CONFIG.read_text())
        if config.get("base_name") != base_name:
            raise LocalERPError("Существующая настройка другой базы не перезаписывается.")
        return config
    config = {"base_name":base_name, "port":port, "username":"local-portal", "password":secrets.token_urlsafe(32)}
    CONFIG.parent.mkdir(exist_ok=True)
    with CONFIG.open("x", encoding="utf-8") as stream:
        os.chmod(CONFIG, 0o600)
        json.dump(config, stream)
    return config
