"""Воспроизводимые метаданные прикладного контура проходной ООО «ЧРЗ»."""
import json
import xml.etree.ElementTree as E
from pathlib import Path
from build_metadata import ROOT, MD, V8, XR, CFG, node, uid, title, save

DEST = ROOT / 'one_c/configuration'
XSI = 'http://www.w3.org/2001/XMLSchema-instance'
FOLDERS = {'Enum': 'Enums', 'Constant': 'Constants', 'AccumulationRegister': 'AccumulationRegisters',
           'InformationRegister': 'InformationRegisters', 'Report': 'Reports', 'Role': 'Roles',
           'Subsystem': 'Subsystems', 'DataProcessor': 'DataProcessors', 'BusinessProcess': 'BusinessProcesses', 'Task': 'Tasks'}


def metadata(kind, name, caption, categories=()):
    root = E.Element('{'+MD+'}MetaDataObject', {'version': '2.20', 'xmlns:cfg': CFG, 'xmlns:xs': 'http://www.w3.org/2001/XMLSchema'})
    obj = node(root, kind); obj.set('uuid', uid(kind+'/'+name))
    if categories:
        info = node(obj, 'InternalInfo')
        for category in categories:
            g = node(info, 'GeneratedType', namespace=XR)
            g.set('name', kind+category+'.'+name); g.set('category', category)
            node(g, 'TypeId', uid(kind+name+category+'type'), XR)
            node(g, 'ValueId', uid(kind+name+category+'value'), XR)
    p = node(obj, 'Properties'); node(p, 'Name', name); title(p, caption)
    return root, obj, p


def value_type(parent, kind, length=150):
    t = node(parent, 'Type')
    node(t, 'Type', ('cfg:' if '.' in kind else 'xs:')+kind, V8)
    if kind == 'string':
        q = node(t, 'StringQualifiers', namespace=V8)
        node(q, 'Length', length, V8); node(q, 'AllowedLength', 'Variable', V8)
    elif kind == 'decimal':
        q = node(t, 'NumberQualifiers', namespace=V8)
        for k, v in [('Digits', 15), ('FractionDigits', 3), ('AllowedSign', 'Any')]: node(q, k, v, V8)


def field(children, owner, category, spec):
    f = node(children, category); f.set('uuid', uid(owner+'/'+category+'/'+spec[0]))
    p = node(f, 'Properties'); node(p, 'Name', spec[0]); title(p, spec[1]); value_type(p, spec[2])
    if category == 'Dimension': node(p, 'Indexing', 'Index')


def form(kind, name, caption, action='Сформировать'):
    """Общая управляемая форма с печатным табличным документом."""
    root, obj, p = metadata('Form', name+'/Main', caption)
    p.find('{'+MD+'}Name').text = 'Main'; node(p, 'FormType', 'Managed')
    save(DEST/FOLDERS[kind]/name/'Forms/Main.xml', root)
    # У пространства формы собственный набор элементов, отличный от метаданных.
    lf = 'http://v8.1c.ru/8.3/xcf/logform'
    f = E.Element('{'+lf+'}Form', {'version': '2.20', 'xmlns:cfg': CFG, 'xmlns:xs': 'http://www.w3.org/2001/XMLSchema'})
    def el(par, key, val=None): return node(par, key, val, lf)
    bar = el(f, 'AutoCommandBar'); bar.set('name', 'Панель'); bar.set('id', '-1')
    items = el(bar, 'ChildItems')
    for i, (command, text) in enumerate([('Generate', action), ('Print', 'Печать')]):
        b = el(items, 'Button'); b.set('name', command); b.set('id', str(10+i))
        el(b, 'Type', 'CommandBarButton'); el(b, 'CommandName', 'Form.Command.'+command)
    items = el(f, 'ChildItems')
    if kind == 'Report':
        for i, (key, text) in enumerate([('PeriodStart', 'Начало периода'), ('PeriodEnd', 'Конец периода')]):
            inp = el(items, 'InputField'); inp.set('name', key); inp.set('id', str(20+i)); el(inp, 'DataPath', key)
    sheet = el(items, 'SpreadSheetDocumentField'); sheet.set('name', 'Result'); sheet.set('id', '1')
    el(sheet, 'DataPath', 'Result'); el(sheet, 'TitleLocation', 'None'); el(sheet, 'Width', '100')
    attrs = el(f, 'Attributes')
    for i, (key, typ) in enumerate([('Object', 'cfg:'+kind+'Object.'+name), ('Result', 'mxl:SpreadsheetDocument')]+
                                  ([('PeriodStart', 'xs:dateTime'), ('PeriodEnd', 'xs:dateTime')] if kind == 'Report' else [])):
        a = el(attrs, 'Attribute'); a.set('name', key); a.set('id', str(i+1))
        t = el(a, 'Type'); v = node(t, 'Type', typ, V8)
        if key == 'Result': v.set('xmlns:mxl', 'http://v8.1c.ru/8.2/data/spreadsheet')
        if i == 0: el(a, 'MainAttribute', 'true')
    commands = el(f, 'Commands')
    for i, (key, text) in enumerate([('Generate', action), ('Print', 'Печать')]):
        c = el(commands, 'Command'); c.set('name', key); c.set('id', str(i+1))
        title_node = el(c, 'Title'); it = node(title_node, 'item', namespace=V8)
        node(it, 'lang', 'ru', V8); node(it, 'content', text, V8); el(c, 'Action', key)
    save(DEST/FOLDERS[kind]/name/'Forms/Main/Ext/Form.xml', f)
    body = ('РезультатСервера = AccessReports.Сформировать("'+name+'", PeriodStart, PeriodEnd);' if kind == 'Report'
            else 'РезультатСервера = AccessAssignmentDemo.Заполнить();')
    bsl = f'''// Команда исполняется на сервере; на клиент передаётся готовая печатная форма.
&НаКлиенте
Процедура Generate(Команда)
    GenerateServer();
КонецПроцедуры

&НаСервере
Процедура GenerateServer()
    {body}
    Result = РезультатСервера;
КонецПроцедуры

&НаКлиенте
Процедура Print(Команда)
    Если Result.ВысотаТаблицы = 0 Тогда
        Сообщить("Сначала сформируйте результат");
        Возврат;
    КонецЕсли;
    Result.Показать("{caption}");
КонецПроцедуры
'''
    if kind == 'Report':
        events = el(f, 'Events'); event = el(events, 'Event', 'ПриСозданииНаСервере'); event.set('name', 'OnCreateAtServer')
        save(DEST/FOLDERS[kind]/name/'Forms/Main/Ext/Form.xml', f)
        bsl += '''
&НаСервере
Процедура ПриСозданииНаСервере(Отказ, СтандартнаяОбработка)
    PeriodStart = НачалоДня(ТекущаяДатаСеанса());
    PeriodEnd = КонецДня(ТекущаяДатаСеанса());
КонецПроцедуры
'''
    (DEST/FOLDERS[kind]/name/'Forms/Main/Ext/Form/Module.bsl').parent.mkdir(parents=True, exist_ok=True)
    (DEST/FOLDERS[kind]/name/'Forms/Main/Ext/Form/Module.bsl').write_text(bsl)


def build():
    specs = json.loads((ROOT/'one_c/assignment.json').read_text())
    tree = E.parse(DEST/'Configuration.xml'); cfg = tree.getroot().find('{'+MD+'}Configuration')
    children = cfg.find('{'+MD+'}ChildObjects')
    def finish(kind, name, root):
        if not any(x.tag == '{'+MD+'}'+kind and x.text == name for x in children): node(children, kind, name)
        save(DEST/FOLDERS[kind]/(name+'.xml'), root)
    for spec in specs['enums']:
        name = spec['name']; root, obj, p = metadata('Enum', name, spec['title'], ['Ref', 'Manager', 'List'])
        ch = node(obj, 'ChildObjects')
        for key, caption in spec['values']:
            e = node(ch, 'EnumValue'); e.set('uuid', uid(name+'/'+key)); pp = node(e, 'Properties'); node(pp, 'Name', key); title(pp, caption)
        finish('Enum', name, root)
    for spec in specs['constants']:
        name = spec['name']; root, obj, p = metadata('Constant', name, spec['title'], ['Manager', 'ValueManager', 'ValueKey'])
        value_type(p, spec['type']); node(p, 'UseStandardCommands', 'true'); finish('Constant', name, root)
    for kind, key in [('AccumulationRegister', 'accumulation_registers'), ('InformationRegister', 'information_registers')]:
        for spec in specs[key]:
            name = spec['name']; root, obj, p = metadata(kind, name, spec['title'], ['Record', 'Manager', 'Selection', 'List', 'RecordSet', 'RecordKey']+(['RecordManager'] if kind == 'InformationRegister' else []))
            node(p, 'UseStandardCommands', 'true'); node(p, 'DataLockControlMode', 'Managed')
            if kind == 'AccumulationRegister': node(p, 'RegisterType', spec.get('register_type', 'Balance'))
            else:
                node(p, 'InformationRegisterPeriodicity', 'Nonperiodical'); node(p, 'WriteMode', 'Independent')
            ch = node(obj, 'ChildObjects')
            for category, field_key in [('Resource', 'resources'), ('Dimension', 'dimensions')]:
                for s in spec[field_key]: field(ch, name, category, s)
            finish(kind, name, root)
    for kind, key in [('Report', 'reports'), ('DataProcessor', 'data_processors')]:
        for spec in specs[key]:
            name = spec['name']; root, obj, p = metadata(kind, name, spec['title'], ['Object', 'Manager'])
            node(p, 'UseStandardCommands', 'true'); node(p, 'DefaultForm', kind+'.'+name+'.Form.Main')
            ch = node(obj, 'ChildObjects'); node(ch, 'Form', 'Main'); finish(kind, name, root)
            form(kind, name, spec['title'], 'Сформировать' if kind == 'Report' else 'Подготовить учебные данные')
    for spec in specs['subsystems']:
        name = spec['name']; root, obj, p = metadata('Subsystem', name, spec['title'])
        node(p, 'IncludeInCommandInterface', 'true'); node(p, 'UseOneCommand', 'false'); content = node(p, 'Content')
        for ref in spec['content']:
            n = node(content, 'Item', ref, XR); n.set('{'+XSI+'}type', 'xr:MDObjectRef')
        node(obj, 'ChildObjects')
        finish('Subsystem', name, root)
    # Маршруты платформы: два последовательных действия с настоящими задачами.
    root, obj, p = metadata('Task', 'AccessTasks', 'Задачи проходной', ['Object', 'Ref', 'Selection', 'List', 'Manager'])
    for k, v in [('UseStandardCommands', 'true'), ('NumberType', 'String'), ('NumberLength', '11'), ('Autonumbering', 'true'), ('DescriptionLength', '150')]: node(p, k, v)
    ch = node(obj, 'ChildObjects')
    for f in [('ActorLogin', 'Исполнитель', 'string'), ('RequiredRole', 'Требуемая роль', 'string')]: field(ch, 'AccessTasks', 'Attribute', f)
    finish('Task', 'AccessTasks', root)
    for name, caption, ref, activities in [
        ('VisitApproval', 'Согласование и выдача пропуска', ('Request', 'Заявка', 'DocumentRef.Requests'), [('Approve', 'Согласовать заявку'), ('Issue', 'Выдать пропуск')]),
        ('IncidentHandling', 'Разбор нарушения', ('Incident', 'Нарушение', 'DocumentRef.SecurityIncidents'), [('Review', 'Разобрать нарушение'), ('Resolve', 'Зафиксировать решение')])]:
        root, obj, p = metadata('BusinessProcess', name, caption, ['Object', 'Ref', 'Selection', 'List', 'Manager', 'RoutePointRef'])
        for k, v in [('UseStandardCommands', 'true'), ('NumberType', 'String'), ('NumberLength', '11'), ('Autonumbering', 'true'), ('Task', 'Task.AccessTasks')]: node(p, k, v)
        ch = node(obj, 'ChildObjects'); field(ch, name, 'Attribute', ref)
        field(ch, name, 'Attribute', ('Resolution', 'Результат рассмотрения', 'string'))
        finish('BusinessProcess', name, root)
        flowchart(name, activities)
    # Включение маршрутов в разделы интерфейса.
    for section, names in [('VisitorAccess', ['BusinessProcess.VisitApproval', 'Task.AccessTasks']), ('GateControl', ['BusinessProcess.IncidentHandling'])]:
        path = DEST/'Subsystems'/(section+'.xml'); t = E.parse(path)
        c = t.getroot().find('.//{'+MD+'}Content')
        for ref in names:
            it = node(c, 'Item', ref, XR); it.set('{'+XSI+'}type', 'xr:MDObjectRef')
        save(path, t.getroot())
    for spec in specs['roles']:
        name = spec['name']; root, obj, p = metadata('Role', name, spec['title']); finish('Role', name, root)
        ns = 'http://v8.1c.ru/8.2/roles'; rights = E.Element('{'+ns+'}Rights', {'version': '2.20'})
        def rnode(par, key, val=None): return node(par, key, val, ns)
        rnode(rights, 'setForNewObjects', 'false'); rnode(rights, 'setForAttributesByDefault', 'true'); rnode(rights, 'independentRightsOfChildObjects', 'false')
        def grant(ref, names):
            o = rnode(rights, 'object'); rnode(o, 'name', ref)
            for right in names:
                item = rnode(o, 'right'); rnode(item, 'name', right); rnode(item, 'value', 'true')
        grant('Configuration.ПодворныйВиталийОлегович70204645', ['ThinClient', 'ThickClient', 'Output']+(['Administration', 'DataAdministration'] if name == 'Administrator' else []))
        for child in children:
            k, objname = child.tag.split('}')[-1], child.text
            if k == 'Catalog':
                grants = ['Read', 'View', 'InputByString']
                if name == 'Administrator': grants += ['Insert', 'Update', 'InteractiveInsert', 'Edit']
                grant(k+'.'+objname, grants)
            elif k == 'Document':
                grants = ['Read', 'View', 'InputByString']
                if name == 'Administrator' or objname in spec['write_documents']:
                    grants += ['Insert', 'Update', 'Posting', 'InteractiveInsert', 'Edit', 'InteractivePosting', 'InteractivePostingRegular']
                grant(k+'.'+objname, grants)
            elif k in ('Report', 'Subsystem'): grant(k+'.'+objname, ['Use'] if k == 'Report' else ['View'])
            elif k in ('AccumulationRegister', 'InformationRegister'):
                grant(k+'.'+objname, ['Read', 'View']+(['Update'] if name in ('Administrator', 'Guard') else []))
            elif k == 'DataProcessor' and name == 'Administrator': grant(k+'.'+objname, ['Use'])
            elif k == 'Constant': grant(k+'.'+objname, ['Read']+(['Update'] if name == 'Administrator' else []))
            elif k in ('BusinessProcess', 'Task'):
                grants = ['Read', 'View', 'InputByString']
                if name in ('Administrator', 'Guard', 'Approver'): grants += ['Insert', 'Update', 'InteractiveInsert', 'Edit']
                if k == 'BusinessProcess' and name in ('Administrator', 'Guard', 'Approver'): grants += ['Start', 'InteractiveStart']
                if k == 'Task' and name in ('Administrator', 'Guard', 'Approver'): grants += ['Execute', 'InteractiveExecute']
                grant(k+'.'+objname, grants)
        save(DEST/'Roles'/name/'Ext/Rights.xml', rights)
    save(DEST/'Configuration.xml', tree.getroot())


def flowchart(name, activities):
    ns = 'http://v8.1c.ru/8.3/xcf/scheme'
    root = E.Element('{'+ns+'}GraphicalSchema', {'version': '2.20', 'xmlns:style': 'http://v8.1c.ru/8.1/data/ui/style'})
    def el(p, key, value=None): return node(p, key, value, ns)
    el(root, 'GridEnabled', 'true'); el(root, 'GridHorizontalStep', '20'); el(root, 'GridVerticalStep', '20')
    items = el(root, 'Items')
    points = [('Start', 'Start', 'Начало'), *[('Activity', k, v) for k, v in activities], ('Completion', 'Finish', 'Завершение')]
    for i, (kind, key, caption) in enumerate(points):
        item = el(items, kind); item.set('id', str(i+1)); item.set('uuid', uid(name+'/route/'+key))
        p = el(item, 'Properties'); el(p, 'Name', key)
        t = el(p, 'Title'); it = node(t, 'item', namespace=V8); node(it, 'lang', 'ru', V8); node(it, 'content', caption, V8)
        el(p, 'TabOrder', str(i+1)); el(p, 'BackColor', 'auto'); el(p, 'TextColor', 'style:FormTextColor'); el(p, 'LineColor', 'style:BorderColor')
        el(p, 'HorizontalAlign', 'Center'); el(p, 'VerticalAlign', 'Center')
        location = el(p, 'Location'); location.attrib.update(top=str(20+i*100), left='100', bottom=str(80+i*100), right='300')
        if kind == 'Activity':
            el(p, 'TaskDescription', caption); el(p, 'Group', 'false'); el(p, 'AddressingAttributes')
            events = el(item, 'Events')
            for event, handler in [('OnCreateTask', key+'Create'), ('OnExecute', key+'Execute')]:
                n = el(events, 'Event', handler); n.set('name', event)
    for i in range(len(points)-1):
        item = el(items, 'ConnectionLine'); item.set('id', str(10+i)); p = el(item, 'Properties'); el(p, 'Name', 'Line'+str(i+1))
        pivots = el(p, 'PivotPoints')
        for y in [80+i*100, 120+i*100]:
            pt = el(pivots, 'Point'); pt.attrib.update(x='200', y=str(y))
        connect = el(p, 'Connect')
        for tag, key, port in [('From', points[i][1], '4'), ('To', points[i+1][1], '2')]:
            end = el(connect, tag); el(end, 'Item', key); el(end, 'PortIndex', port)
        el(p, 'EndArrow', 'Filled'); el(p, 'DecorativeLine', 'false')
    save(DEST/'BusinessProcesses'/name/'Ext/Flowchart.xml', root)


if __name__ == '__main__': build()
