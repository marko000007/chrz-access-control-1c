Функция Самопроверка() Экспорт
    Каталоги = AccessCatalogs.Самопроверка();
    Политика = AccessPolicy.Самопроверка();
    Заявки = AccessRequests.Самопроверка();
    Согласование = AccessApprovals.Самопроверка();
    Команды = AccessCommands.Самопроверка();
    Пропуска = AccessPasses.Самопроверка();
    Возврат Новый Структура("ok,catalogs,policy,requests,approvals,commands,passes,data_origin", Истина, Каталоги, Политика, Заявки, Согласование, Команды, Пропуска, "synthetic");
КонецФункции
