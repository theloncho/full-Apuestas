from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def odds_format(value):
    """
    Formatea un valor decimal de cuotas a exactamente 2 decimales
    utilizando el separador de punto en lugar de coma.
    Ej: 3.9956 -> "4.00"
    """
    try:
        val = Decimal(str(value))
        return f"{val:.2f}"
    except (ValueError, TypeError, Exception):
        return value

@register.filter
def sort_1x2(selections):
    """
    Ordena las selecciones de un mercado 1X2 para que siempre aparezcan
    en el orden: '1' (Local), 'X' (Empate), '2' (Visita).
    Cualquier otra selección se añade al final.
    """
    order = {'1': 0, 'X': 1, '2': 2}
    
    # Convertir a lista para poder iterar sin problemas
    sel_list = list(selections)
    
    return sorted(
        sel_list,
        key=lambda s: order.get(s.name, 99)
    )

@register.filter
def initial(value):
    """
    Devuelve la primera letra de un string en mayúscula.
    Útil para crear avatares de equipos.
    """
    if value and isinstance(value, str):
        return value[0].upper()
    return '?'
