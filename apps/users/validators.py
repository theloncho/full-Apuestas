from django.core.exceptions import ValidationError
from .models import validate_dni_peruano
from datetime import date


def validate_age(birth_date):
    """Valida que el usuario tenga al menos 18 años."""
    today = date.today()
    age = today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )
    if age < 18:
        raise ValidationError(
            "Debes ser mayor de 18 años para registrarte."
        )


def validate_dni(dni):
    """Valida el DNI peruano con algoritmo de dígito verificador."""
    if not validate_dni_peruano(dni):
        raise ValidationError(
            "DNI inválido. Verifica el número ingresado."
        )
