from __future__ import annotations

from typing import Any

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models


class EncryptedCharField(models.CharField):
    """A CharField that transparently encrypts and decrypts values.

    Uses Fernet symmetric encryption keyed from ``settings.FIELD_ENCRYPTION_KEY``.
    """

    description = "Encrypted char field"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._fernet: Fernet | None = None
        super().__init__(*args, **kwargs)

    def _get_fernet(self) -> Fernet:
        if self._fernet is None:
            key = getattr(settings, "FIELD_ENCRYPTION_KEY", None)
            if not key:
                raise RuntimeError("FIELD_ENCRYPTION_KEY is not set in Django settings")
            self._fernet = Fernet(key.encode("utf-8"))
        return self._fernet

    def get_prep_value(self, value: Any) -> str:
        value = super().get_prep_value(value)
        if value is None:
            return None  # type: ignore[return-value]
        return self._get_fernet().encrypt(str(value).encode("utf-8")).decode("utf-8")

    def from_db_value(self, value: Any, expression: Any, connection: Any) -> str | None:
        if value is None:
            return None
        return self._get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")


class EncryptedTextField(models.TextField):
    """A TextField that transparently encrypts and decrypts values.

    Uses Fernet symmetric encryption keyed from ``settings.FIELD_ENCRYPTION_KEY``.
    """

    description = "Encrypted text field"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._fernet: Fernet | None = None
        super().__init__(*args, **kwargs)

    def _get_fernet(self) -> Fernet:
        if self._fernet is None:
            key = getattr(settings, "FIELD_ENCRYPTION_KEY", None)
            if not key:
                raise RuntimeError("FIELD_ENCRYPTION_KEY is not set in Django settings")
            self._fernet = Fernet(key.encode("utf-8"))
        return self._fernet

    def get_prep_value(self, value: Any) -> str:
        value = super().get_prep_value(value)
        if value is None:
            return None  # type: ignore[return-value]
        return self._get_fernet().encrypt(str(value).encode("utf-8")).decode("utf-8")

    def from_db_value(self, value: Any, expression: Any, connection: Any) -> str | None:
        if value is None:
            return None
        return self._get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
