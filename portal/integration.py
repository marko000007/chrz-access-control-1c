"""Bounded HTTP client; domain records remain in 1C."""
import base64
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from django.conf import settings


class ERPUnavailable(Exception):
    pass


class ERPNotConfigured(ERPUnavailable):
    pass


class ERPForbidden(ERPUnavailable):
    pass


class ERPConflict(ERPUnavailable):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ERPClient:
    MAX_RESPONSE = 1024 * 1024

    def __init__(self, base_url, username, password, timeout=5):
        if not base_url or not username or not password:
            raise ERPNotConfigured("Сервис учёта 1С ещё не настроен.")
        parsed=urlsplit(base_url)
        if parsed.scheme not in {"http","https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ERPNotConfigured("Некорректный адрес сервиса 1С.")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost","127.0.0.1","::1"}:
            raise ERPNotConfigured("Для удалённой 1С требуется HTTPS.")
        if type(timeout) not in (float,int) or not 0 < timeout <= 30:
            raise ERPNotConfigured("Недопустимый таймаут интеграции.")
        self.base_url=base_url.rstrip("/")
        self.authorization="Basic "+base64.b64encode((username+":"+password).encode("utf-8")).decode("ascii")
        self.timeout=timeout
        self.opener=build_opener(NoRedirect())

    def request(self, method, path, actor, payload=None, idempotency_key=None):
        if method not in {"GET","POST"} or not path.startswith("/") or path.startswith("//") or ".." in path or urlsplit(path).query or urlsplit(path).fragment:
            raise ValueError("Недопустимый маршрут интеграции.")
        if not isinstance(actor,str) or not actor or len(actor)>150 or any(ord(c)<32 for c in actor):
            raise ValueError("Некорректный автор запроса.")
        actor64=base64.b64encode(actor.encode("utf-8")).decode("ascii")
        headers={"Authorization":self.authorization,"Accept":"application/json","Content-Type":"application/json; charset=utf-8","X-Portal-Actor":actor64}
        if method == "POST":
            from uuid import UUID
            try:
                key=str(UUID(str(idempotency_key)))
            except (ValueError,TypeError,AttributeError) as exc:
                raise ValueError("Для изменения нужен UUID Idempotency-Key.") from exc
            headers["Idempotency-Key"]=key
        data=None if payload is None else json.dumps(payload,ensure_ascii=False,allow_nan=False).encode("utf-8")
        if data is not None and len(data)>128*1024:
            raise ValueError("Запрос слишком велик.")
        request=Request(self.base_url+path,data=data,headers=headers,method=method)
        try:
            with self.opener.open(request,timeout=self.timeout) as response:
                if response.headers.get_content_type() != "application/json":
                    raise ERPUnavailable("1С вернула ответ неизвестного формата.")
                raw=response.read(self.MAX_RESPONSE+1)
        except HTTPError as exc:
            exc.close()
            if exc.code in {401,403}:
                raise ERPForbidden("1С не разрешила выполнение действия.") from None
            if exc.code == 409:
                raise ERPConflict("Состояние записи изменилось или запрос конфликтует с предыдущим.") from None
            raise ERPUnavailable("Не удалось выполнить запрос к 1С.") from None
        except (URLError,TimeoutError,OSError):
            raise ERPUnavailable("Сервис 1С временно недоступен.") from None
        if len(raw)>self.MAX_RESPONSE:
            raise ERPUnavailable("Ответ 1С превышает допустимый размер.")
        try:
            result=json.loads(raw)
        except (ValueError,UnicodeDecodeError):
            raise ERPUnavailable("Не удалось прочитать JSON 1С.") from None
        if not isinstance(result,dict) or type(result.get("api_version")) is not int or result["api_version"] != 1 or "data" not in result:
            raise ERPUnavailable("Версия или структура API 1С не поддерживается.")
        return result["data"]

    def health(self, actor):
        data=self.request("GET","/health",actor)
        if not isinstance(data,dict) or data.get("system") != "1c-enterprise":
            raise ERPUnavailable("Сервис не подтвердил ожидаемый контракт 1С.")
        return data


def get_client():
    return ERPClient(settings.ERP_BASE_URL,settings.ERP_USERNAME,settings.ERP_PASSWORD)
