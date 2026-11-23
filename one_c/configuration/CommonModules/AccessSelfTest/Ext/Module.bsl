Функция Самопроверка() Экспорт
    Каталоги = AccessCatalogs.Самопроверка();
    Политика = AccessPolicy.Самопроверка();
    Заявки = AccessRequests.Самопроверка();
    Согласование = AccessApprovals.Самопроверка();
    Команды = AccessCommands.Самопроверка();
    Возврат Новый Структура("ok,catalogs,policy,requests,approvals,commands,data_origin", Истина, Каталоги, Политика, Заявки, Согласование, Команды, "synthetic");
КонецФункции
