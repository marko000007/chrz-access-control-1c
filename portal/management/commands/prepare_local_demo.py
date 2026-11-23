"""Локальные вымышленные аккаунты; существующие пароли не изменяются."""
import json
import os
from pathlib import Path
import secrets
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Подготовить четыре локальных демоаккаунта и сохранить начальные пароли вне Git"

    def handle(self, *args, **options):
        directory = Path(settings.BASE_DIR)/".local"
        directory.mkdir(exist_ok=True)
        path = directory/"demo-accounts.json"
        credentials = json.loads(path.read_text()) if path.exists() else {}
        created = 0
        with transaction.atomic():
            for role in ["admin", "requester", "approver", "guard"]:
                name = "demo."+role
                if get_user_model().objects.filter(username=name).exists():
                    continue
                password = secrets.token_urlsafe(24)
                user = get_user_model().objects.create_user(name, password=password)
                if role == "admin":
                    user.is_staff = True; user.is_superuser = True
                    user.save(update_fields=["is_staff", "is_superuser"])
                credentials[name] = password
                created += 1
            temporary = directory/".demo-accounts.pending"
            with temporary.open("w", encoding="utf-8") as stream:
                os.chmod(temporary, 0o600)
                json.dump(credentials, stream, ensure_ascii=False, indent=2)
            temporary.replace(path)
        self.stdout.write(f"Создано демоаккаунтов: {created}. Начальные пароли: {path}. Существующие аккаунты не изменены.")
