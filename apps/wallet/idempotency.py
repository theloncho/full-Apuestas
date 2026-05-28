from django.core.cache import cache
import json


IDEMPOTENCY_TTL = 86400  # 24 horas


def idempotent_view(view_func):
    """
    Decorator para endpoints que requieren idempotencia.
    El cliente envía X-Idempotency-Key: <uuid> o idempotency_key en POST.
    Si la key ya existe, retorna la respuesta guardada.
    """
    def wrapper(request, *args, **kwargs):
        key = (
            request.headers.get('X-Idempotency-Key')
            or request.POST.get('idempotency_key')
        )
        if not key:
            return view_func(request, *args, **kwargs)

        user_id = request.user.id if request.user.is_authenticated else 'anon'
        cache_key = f'idem:{key}:{user_id}'
        cached = cache.get(cache_key)
        if cached is not None:
            from django.http import JsonResponse
            return JsonResponse(json.loads(cached), status=200)

        response = view_func(request, *args, **kwargs)

        # Guardar solo respuestas exitosas
        if hasattr(response, 'status_code') and response.status_code in (200, 201):
            try:
                cache.set(cache_key, response.content.decode(), IDEMPOTENCY_TTL)
            except Exception:
                pass

        return response
    return wrapper
