"""Запуск loopback-адаптера к установленной файловой 1С."""
import argparse
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from portal.local_gateway import OneCRuntime, create_server, save_configuration


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["setup", "serve"])
    parser.add_argument("--base-name", default="development")
    parser.add_argument("--user", help="Имя локального Django-администратора для первичной настройки")
    parser.add_argument('--allow-gui-1c',action='store_true')
    args=parser.parse_args()
    if args.allow_gui_1c:os.environ['ONE_C_ALLOW_GUI']='1'
    if args.operation=='setup' and os.getenv('ONE_C_ALLOW_GUI','0')!='1':
        parser.error('Подготовка1С требует явно включённого интерактивного режима --allow-gui-1c.')
    runtime=OneCRuntime(args.base_name)
    if args.operation=="setup":
        if not args.user: parser.error("Для setup укажите --user")
        status, result=runtime.invoke({"operation":"setup", "actor":args.user})
        if status != 200: raise SystemExit("Первичная настройка 1С не выполнена.")
        save_configuration(args.base_name)
        print("Локальная 1С подготовлена. Учебные данные вымышлены; ключ адаптера сохранён локально.")
    else:
        config=save_configuration(args.base_name)
        server=create_server(runtime,config['username'],config['password'],config['port'])
        print(f"Локальный адаптер 1С: http://127.0.0.1:{server.server_port}")
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally: server.server_close()


if __name__=="__main__":main()
