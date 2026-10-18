from django.db import models

from apps.integrations.crypto import decrypt_str, encrypt_str


class EncryptedTextField(models.TextField):
    description = "Texto cifrado en reposo con la llave de aplicación."

    def from_db_value(self, value, expression, connection):
        if not value:
            return value
        return decrypt_str(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value:
            return value
        return encrypt_str(value)
