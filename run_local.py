"""Local IDE entry point: migrate, check, then start one loopback server."""
import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

BASE_DIR = Path(__file__).resolve().parent
PORT = 8044


def main():
    parser = argparse.ArgumentParser(description="Локальный запуск приложения")
    parser.add_argument("--setup-demo", action="store_true", help="Однократно собрать локальную1С и вымышленные демоаккаунты")
    parser.add_argument("--check", action="store_true", help="Подготовить базу и проверить конфигурацию без запуска сервера")
    parser.add_argument("--port", type=int, default=PORT, help="Локальный порт приложения")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Порт должен быть от 1024 до 65535")
    os.chdir(BASE_DIR)
    database_url = os.getenv("DATABASE_URL", "")
    if database_url:
        host = unquote(urlsplit(database_url).hostname or "localhost")
        if host not in {"localhost", "127.0.0.1", "::1"} and not host.startswith("/"):
            raise SystemExit("Локальный запуск требует локальную DATABASE_URL. Удалите переменную для SQLite или укажите PostgreSQL на этом компьютере.")
    erp_url = os.getenv("ERP_BASE_URL", "")
    if erp_url and urlsplit(erp_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit("Для локального запуска укажите локальный адрес сервиса 1С.")
    os.environ["DEBUG"] = "1"
    os.environ["ALLOWED_HOSTS"] = "127.0.0.1,localhost"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    from django.core.management import call_command
    django.setup()
    call_command("migrate", interactive=False, verbosity=0)
    call_command("check", verbosity=0)
    if args.setup_demo:
        if erp_url:
            raise SystemExit("Для подготовки комплектной базы уберите ERP_BASE_URL из окружения.")
        for operation in ["create", "load", "check"]:
            subprocess.run([sys.executable, str(BASE_DIR/"scripts/one_c.py"), operation], cwd=BASE_DIR, check=True)
        call_command("prepare_local_demo")
        from portal.local_gateway import OneCRuntime, save_configuration
        runtime = OneCRuntime()
        if runtime.invoke({"operation":"setup", "actor":"demo.admin"})[0] != 200:
            raise SystemExit("Первичная настройка1С не подтверждена.")
        save_configuration("development")
    gateway = None
    gateway_thread = None
    if not erp_url and (BASE_DIR/".local/local-erp.json").is_file():
        import json
        import threading
        from django.conf import settings
        from portal.local_gateway import CONFIG, OneCRuntime, create_server
        config = json.loads(CONFIG.read_text())
        runtime = OneCRuntime(config["base_name"])
        if not args.check:
            gateway = create_server(runtime, config["username"], config["password"], config["port"])
            gateway_thread = threading.Thread(target=gateway.serve_forever, daemon=True)
            gateway_thread.start()
            settings.ERP_BASE_URL = "http://127.0.0.1:"+str(gateway.server_port)
            settings.ERP_USERNAME = config["username"]
            settings.ERP_PASSWORD = config["password"]
            settings.ERP_TIMEOUT = 30
    if args.check:
        print("Локальная конфигурация проверена: http://127.0.0.1:" + str(args.port))
        return
    try:
        call_command("runserver", "127.0.0.1:" + str(args.port), use_reloader=False)
    finally:
        if gateway:
            gateway.shutdown()
            gateway.server_close()
            gateway_thread.join(timeout=3)


if __name__ == "__main__":
    main()
