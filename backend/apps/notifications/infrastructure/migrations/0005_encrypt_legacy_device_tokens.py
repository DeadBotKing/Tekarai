"""Encrypt device push tokens created before Phase 15."""

import base64
import hashlib
import hmac
import os

from django.conf import settings
from django.db import migrations

_PREFIX = "ntf1."


def _stream(key, nonce, length):
    blocks = []
    counter = 0
    while sum(map(len, blocks)) < length:
        blocks.append(hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1
    return b"".join(blocks)[:length]


def encrypt_legacy_tokens(apps, schema_editor):
    Device = apps.get_model("notifications", "NotificationDeviceModel")
    key = hashlib.sha256(("tekarai.notifications:" + settings.SECRET_KEY).encode()).digest()
    for device in Device.objects.all().only("id", "pushToken").iterator(chunk_size=500):
        value = device.pushToken
        if not value or value.startswith(_PREFIX):
            continue
        raw = value.encode("utf-8")
        nonce = os.urandom(16)
        encrypted = bytes(a ^ b for a, b in zip(raw, _stream(key, nonce, len(raw)), strict=True))
        tag = hmac.new(key, nonce + encrypted, hashlib.sha256).digest()
        envelope = _PREFIX + base64.urlsafe_b64encode(nonce + tag + encrypted).decode("ascii")
        Device.objects.filter(id=device.id).update(pushToken=envelope)


def decrypt_tokens(apps, schema_editor):
    Device = apps.get_model("notifications", "NotificationDeviceModel")
    key = hashlib.sha256(("tekarai.notifications:" + settings.SECRET_KEY).encode()).digest()
    for device in Device.objects.all().only("id", "pushToken").iterator(chunk_size=500):
        value = device.pushToken
        if not value.startswith(_PREFIX):
            continue
        packed = base64.urlsafe_b64decode(value[len(_PREFIX) :].encode("ascii"))
        nonce, tag, encrypted = packed[:16], packed[16:48], packed[48:]
        expected = hmac.new(key, nonce + encrypted, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise ValueError("Cannot reverse migration: token authentication failed")
        raw = bytes(
            a ^ b for a, b in zip(encrypted, _stream(key, nonce, len(encrypted)), strict=True)
        )
        Device.objects.filter(id=device.id).update(pushToken=raw.decode("utf-8"))


class Migration(migrations.Migration):
    dependencies = [("notifications", "0004_alter_notificationdevicemodel_pushtoken")]
    operations = [migrations.RunPython(encrypt_legacy_tokens, decrypt_tokens)]
