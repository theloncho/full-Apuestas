from django.conf import settings


def responsible_gambling(request):
    """Inyecta el mensaje de juego responsable en todos los templates."""
    return {
        'RESPONSIBLE_GAMBLING_MESSAGE': settings.RESPONSIBLE_GAMBLING_MESSAGE,
    }
