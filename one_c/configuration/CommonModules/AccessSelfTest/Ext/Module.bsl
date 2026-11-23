Функция Самопроверка() Экспорт
    Каталоги = AccessCatalogs.Самопроверка();
    Политика = AccessPolicy.Самопроверка();
    Заявки = AccessRequests.Самопроверка();
    Согласование = AccessApprovals.Самопроверка();
    Возврат Новый Структура("ok,catalogs,policy,requests,approvals,data_origin", Истина, Каталоги, Политика, Заявки, Согласование, "synthetic");
КонецФункции
