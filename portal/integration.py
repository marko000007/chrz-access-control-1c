"""Bounded HTTP client; domain records remain in 1C."""
import base64
import json
from datetime import datetime, time, timedelta, timezone
from uuid import UUID
from http.client import HTTPException
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


class ERPMissing(ERPUnavailable):
    pass


class ERPConflict(ERPUnavailable):
    pass


class ERPRejected(ERPUnavailable):
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
            if exc.code == 404:
                raise ERPMissing("Запись не найдена или недоступна.") from None
            if exc.code == 409:
                raise ERPConflict("Состояние записи изменилось или запрос конфликтует с предыдущим.") from None
            if exc.code == 400:
                raise ERPRejected("1С отклонила параметры или текущее состояние команды. Обновите данные.") from None
            raise ERPUnavailable("Не удалось выполнить запрос к 1С.") from None
        except (URLError,TimeoutError,OSError,HTTPException):
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

    def references(self, actor):
        data=self.request("GET","/references",actor)
        if not isinstance(data,dict):
            raise ERPUnavailable("1С вернула некорректные справочники.")
        result={}
        for kind in ["visitors","employees","checkpoints","purposes"]:
            values=data.get(kind)
            if not isinstance(values,list) or len(values)>500:
                raise ERPUnavailable("Неизвестный формат или слишком большой справочник 1С.")
            checked=[]
            seen=set()
            for item in values:
                try:
                    if not isinstance(item,dict):raise ValueError
                    key=str(UUID(item["id"]))
                    if not isinstance(item["name"],str) or not 1 <= len(item["name"]) <= 150 or key in seen:raise ValueError
                except (KeyError,TypeError,ValueError,AttributeError):
                    raise ERPUnavailable("Недопустимая запись справочника 1С.") from None
                checked.append({"id":key,"name":item["name"]});seen.add(key)
            result[kind]=checked
        return result

    def requests(self, actor):
        data=self.request("GET","/requests",actor)
        if not isinstance(data,dict) or not isinstance(data.get("items"),list) or len(data["items"])>100:
            raise ERPUnavailable("Некорректный список заявок 1С.")
        result=[]
        for item in data["items"]:
            try:
                if not isinstance(item,dict):raise ValueError
                key=str(UUID(item["id"]))
                author=item["requester_login"]
                visitor=item["visitor"]
                if not isinstance(author,str) or not 1 <= len(author) <= 150 or not isinstance(visitor,str) or not 1 <= len(visitor) <= 150:raise ValueError
                if item["status"] not in {"submitted","approved","rejected","cancelled"}:raise ValueError
                dates={}
                for field in ["starts_at","ends_at"]:
                    value=datetime.fromisoformat(item[field])
                    if value.tzinfo is None:raise ValueError
                    dates[field]=value
                if dates["ends_at"]<=dates["starts_at"]:raise ValueError
            except (KeyError,TypeError,ValueError,AttributeError):
                raise ERPUnavailable("Некорректная запись заявки 1С.") from None
            result.append({"id":key,"visitor":visitor,"requester_login":author,"status":item["status"],**dates})
        return result

    def request_detail(self, actor, identifier):
        identifier=str(UUID(str(identifier)))
        data=self.request("GET","/requests/"+identifier,actor)
        try:
            value=dict(data["item"])
            if str(UUID(value["id"])) != str(identifier):raise ValueError
            for field in ["visitor","host","checkpoint","purpose","requester_login"]:
                if not isinstance(value[field],str) or not 1<=len(value[field])<=150:raise ValueError
            for field in ["decision_by","decision_reason"]:
                if not isinstance(value[field],str) or len(value[field])>150:raise ValueError
            if value["status"] not in {"submitted","approved","rejected","cancelled"}:raise ValueError
            for field in ["starts_at","ends_at","created_at","decision_at"]:
                if field=="decision_at" and value.get(field) is None:continue
                value[field]=datetime.fromisoformat(value[field])
                if value[field].tzinfo is None:raise ValueError
            if value["ends_at"]<=value["starts_at"]:raise ValueError
            if (value["status"]=="submitted") != (value["decision_at"] is None):raise ValueError
        except (KeyError,TypeError,ValueError,AttributeError):
            raise ERPUnavailable("Некорректная карточка заявки 1С.") from None
        return value

    def create_request(self, actor, payload, key):
        result=self.request("POST","/requests",actor,payload,key)
        try:
            if not isinstance(result,dict) or result.get("status")!="submitted":raise ValueError
            identifier=str(UUID(result["id"]))
        except (KeyError,TypeError,ValueError,AttributeError):
            raise ERPUnavailable("1С не подтвердила создание заявки.") from None
        return {"id":identifier,"status":"submitted"}

    def actor(self, actor):
        data=self.request("GET","/actors/me",actor)
        if not isinstance(data,dict) or data.get("actor") != actor or data.get("role") not in {"admin","requester","approver","guard"}:
            raise ERPUnavailable("1С вернула некорректное сопоставление пользователя.")
        return data

    def passes(self, actor):
        return self._collection(actor, "/passes", "pass")

    def events(self, actor):
        return self._collection(actor, "/events", "event")

    def _collection(self, actor, path, kind):
        return self._parse_collection(self.request("GET", path, actor), kind)

    def _parse_collection(self, data, kind, maximum=100):
        try:
            items = data["items"]
            if not isinstance(items, list) or len(items)>maximum: raise ValueError
            checked = []
            seen = set()
            for item in items:
                if not isinstance(item, dict): raise ValueError
                value = dict(item)
                value["id"] = str(UUID(value["id"]))
                if value["id"] in seen: raise ValueError
                seen.add(value["id"])
                for key in ["visitor", "checkpoint", "requester_login"]:
                    if not isinstance(value[key], str) or not 1 <= len(value[key]) <= 150: raise ValueError
                if kind == "pass":
                    for key in ["request_id", "checkpoint_id"]: value[key] = str(UUID(value[key]))
                    if value["state"] not in {"active", "revoked"} or value["position"] not in {"inside", "outside"}: raise ValueError
                    dates = ["starts_at", "ends_at", "issued_at"]
                else:
                    value["pass_id"] = str(UUID(value["pass_id"]))
                    if value["direction"] not in {"in", "out"}: raise ValueError
                    if not isinstance(value["actor"], str) or not 1 <= len(value["actor"]) <= 150: raise ValueError
                    dates = ["occurred_at"]
                for key in dates:
                    value[key] = datetime.fromisoformat(value[key])
                    if value[key].tzinfo is None: raise ValueError
                if kind == "pass" and value["ends_at"] <= value["starts_at"]: raise ValueError
                checked.append(value)
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ERPUnavailable("1С вернула некорректный список пропусков или событий.") from None
        return checked

    def movement_report(self, actor, start, end):
        path=f"/reports/movements/{start:%Y%m%d}/{end:%Y%m%d}"
        data=self.request("GET",path,actor)
        items=self._parse_collection(data,"event",maximum=1000)
        try:
            checked={key:datetime.fromisoformat(data[key]) for key in ["starts_at","ends_at","generated_at"]}
            if any(value.tzinfo is None for value in checked.values()):raise ValueError
            if checked["starts_at"]!=datetime.combine(start,time.min,timezone.utc):raise ValueError
            if checked["ends_at"]!=datetime.combine(end+timedelta(days=1),time.min,timezone.utc):raise ValueError
            if any(not checked["starts_at"]<=row["occurred_at"]<checked["ends_at"] for row in items):raise ValueError
            for direction,key in [("in","count_in"),("out","count_out")]:
                if type(data[key]) is not int or data[key]!=sum(row["direction"]==direction for row in items):raise ValueError
        except (KeyError,TypeError,ValueError,AttributeError,OverflowError):
            raise ERPUnavailable("Некорректный период или итоги отчёта 1С.") from None
        return {**checked,"items":items,"count_in":data["count_in"],"count_out":data["count_out"]}

    def decide_request(self, actor, identifier, action, expected_status, reason, key):
        states = {"approve":"approved", "reject":"rejected", "cancel":"cancelled"}
        if action not in states: raise ValueError("Неизвестное решение")
        result = self.request("POST", "/requests/"+action, actor,
            {"id":str(identifier), "expected_status":expected_status, "reason":reason}, key)
        if not isinstance(result, dict) or result.get("id") != str(identifier) or result.get("status") != states[action]:
            raise ERPUnavailable("1С не подтвердила решение.")
        return result

    def issue_pass(self, actor, request_id, key):
        result = self.request("POST", "/passes", actor, {"request_id":str(request_id)}, key)
        return self._pass_result(result, "active")

    def revoke_pass(self, actor, identifier, reason, key):
        result = self.request("POST", "/passes/revoke", actor, {"id":str(identifier), "reason":reason}, key)
        return self._pass_result(result, "revoked")

    @staticmethod
    def _pass_result(result, state):
        try:
            if not isinstance(result, dict) or result.get("state") != state or result.get("position") not in {"inside", "outside"}: raise ValueError
            result["id"] = str(UUID(result["id"]))
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ERPUnavailable("1С не подтвердила команду пропуска.") from None
        return result

    def movement(self, actor, identifier, checkpoint_id, direction, key):
        if direction not in {"in", "out"}: raise ValueError("Неизвестное направление")
        result = self.request("POST", "/movements", actor,
            {"pass_id":str(identifier), "checkpoint_id":str(checkpoint_id), "direction":direction}, key)
        try:
            if not isinstance(result, dict) or result.get("pass_id") != str(identifier) or result.get("direction") != direction: raise ValueError
            result["id"] = str(UUID(result["id"]))
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ERPUnavailable("1С не подтвердила запись прохода.") from None
        return result

    def health(self, actor):
        data=self.request("GET","/health",actor)
        if not isinstance(data,dict) or data.get("system") != "1c-enterprise":
            raise ERPUnavailable("Сервис не подтвердил ожидаемый контракт 1С.")
        return data


def get_client():
    return ERPClient(settings.ERP_BASE_URL,settings.ERP_USERNAME,settings.ERP_PASSWORD,timeout=settings.ERP_TIMEOUT)
