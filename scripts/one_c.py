"""Build only this project's local development infobase."""
import argparse
import os
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
LOCAL=ROOT/".local/1c"
DEFAULT="/Applications/1cv8t.localized/8.3.27.1606/1cv8t.app/Contents/MacOS/1cv8t"


def command(arguments,label,timeout=40):
    if os.getenv("ONE_C_ALLOW_GUI","0")!="1":raise SystemExit("Запуск платформы отключён; нужен явный интерактивный режим.")
    binary=Path(os.getenv("ONE_C_BINARY",DEFAULT))
    if not binary.is_file():raise SystemExit("Укажите ONE_C_BINARY с установленной платформой 1С")
    LOCAL.mkdir(parents=True,exist_ok=True)
    log=LOCAL/(label+".log");log.unlink(missing_ok=True)
    result=subprocess.run([str(binary),*arguments,"/Out",str(log)],cwd=binary.parent,capture_output=True,timeout=timeout)
    text=log.read_text(encoding="utf-8-sig",errors="replace") if log.exists() else ""
    print(label,":",result.returncode)
    if text.strip():print(text.strip())
    if result.returncode:raise SystemExit("Пакетная операция 1С не завершена")
    return text


def main():
    global LOCAL
    parser=argparse.ArgumentParser();parser.add_argument("operation",choices=["create","load","check","dump","smoke"])
    parser.add_argument("--base-name",default="development",help="Имя отдельной базы внутри .local/1c")
    parser.add_argument('--allow-gui',action='store_true',help='Явно разрешить интерактивный запуск платформы')
    args=parser.parse_args()
    if not args.allow_gui and os.getenv('ONE_C_ALLOW_GUI','0')!='1':
        parser.error('Запуск платформы отключён. Для интерактивной операции требуется --allow-gui.')
    if args.allow_gui:os.environ["ONE_C_ALLOW_GUI"]="1"
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}",args.base_name):parser.error("Недопустимое имя базы")
    workspace=LOCAL
    base=workspace/args.base_name
    LOCAL=workspace/"logs"/args.base_name
    if args.operation=="create":
        if (base/"1Cv8.1CD").is_file():print("База уже существует; не перезаписывается");return
        result=LOCAL/"create-result.txt";result.unlink(missing_ok=True)
        command(["CREATEINFOBASE",f'File="{base}";',"/DumpResult",str(result)],"create")
        if not result.exists() or result.read_text(encoding="utf-8-sig").strip()!="0" or not (base/"1Cv8.1CD").is_file():raise SystemExit("Создание базы не подтверждено")
        return
    if not (base/"1Cv8.1CD").is_file():raise SystemExit("Сначала создайте отдельную базу командой create")
    if args.operation=="smoke":
        result=LOCAL/"smoke.json";result.unlink(missing_ok=True)
        command(["ENTERPRISE","/F",str(base),"/C","selftest:"+str(result),"/DisableStartupMessages","/DisableStartupDialogs"],"runtime")
        if not result.exists() or json.loads(result.read_text(encoding="utf-8-sig")).get("ok") is not True:raise SystemExit("Самопроверка 1С не подтверждена; изучите smoke.json и runtime.log")
        print("Самопроверка 1С подтверждена")
        return
    prefix=["DESIGNER","/F",str(base),"/DisableStartupDialogs","/DisableStartupMessages"]
    if args.operation=="load":
        command(prefix+["/LoadConfigFromFiles",str(ROOT/"one_c/configuration")],"load")
        command(prefix+["/UpdateDBCfg"],"update")
    elif args.operation=="check":
        text=command(prefix+["/CheckConfig","-ConfigLogIntegrity","-IncorrectReferences","-ThinClient","-Server"],"check")
        if text.strip() not in {"", "No errors found", "Ошибок не обнаружено", "Ошибок не обнаружено."}:raise SystemExit("Проверка выдала дополнительные сообщения; изучите check.log")
    else:
        target=LOCAL/"normalized-source";target.mkdir(exist_ok=True)
        command(prefix+["/DumpConfigToFiles",str(target)],"dump")
        print("Нормализованные исходники:",target)


if __name__=="__main__":main()
