"""Техническая очередь подтверждений; предметные записи хранятся в1С."""
import uuid
from django.conf import settings
from django.db import models


class PendingCommand(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    context = models.CharField(max_length=100)
    key = models.UUIDField(default=uuid.uuid4, unique=True)
    payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "context"], name="unique_owner_command_context")]
