Функция Самопроверка() Экспорт
    Каталоги = AccessCatalogs.Самопроверка();
    Политика = AccessPolicy.Самопроверка();
    Заявки = AccessRequests.Самопроверка();
    Возврат Новый Структура("ok,catalogs,policy,requests,data_origin", Истина, Каталоги, Политика, Заявки, "synthetic");
КонецФункции
