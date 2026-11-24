"""Неблокирующий межпроцессный слот отправки одного оператора на macOS/Linux."""
from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import stat
from django.conf import settings
from django.db import connection
from django.core.exceptions import ValidationError


@contextmanager
def sending_slot(user):
    root=Path(settings.BASE_DIR)/'.local/command-locks'
    identity=str(connection.settings_dict['NAME'])+'\0'+str(user.pk)
    name=hashlib.sha256(identity.encode()).hexdigest()+'.lock'
    descriptor=None
    try:
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if root.is_symlink():raise OSError('Lock directory is a symlink')
        descriptor=os.open(root/name,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):raise OSError('Not a lock file')
        os.fchmod(descriptor,0o600)
        fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        if descriptor is not None:os.close(descriptor)
        raise ValidationError('Другая команда этого оператора ещё отправляется. Дождитесь ответа и повторите сохранённую форму.') from None
    except OSError:
        if descriptor is not None:os.close(descriptor)
        raise ValidationError('Не удалось получить локальный слот отправки. Команда не отправлена; проверьте доступ к папке проекта.') from None
    try:
        yield
    finally:
        # Файл остаётся:удаление inode создаёт гонку между разными процессами.
        os.close(descriptor)
