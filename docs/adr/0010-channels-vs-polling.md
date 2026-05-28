# ADR 0010: Django Channels vs Polling para Cuotas

**Fecha:** 2026-05-27
**Estado:** Aceptado

## Contexto
Las cuotas en apuestas deportivas cambian constantemente. Es imperativo que el cliente refleje los cambios con la menor latencia posible.

## Opciones Consideradas
1. **Short Polling:** El cliente hace peticiones HTTP GET cada 2-3 segundos.
2. **WebSockets (Django Channels):** Conexión persistente bi-direccional.

## Decisión
Se ha optado por **Django Channels con Redis como Channel Layer**. El frontend (Alpine.js) se suscribirá a un grupo específico del evento (ej. `odds_5`). Cada vez que la cuota cambie, el servidor enviará un payload JSON con la actualización.

## Consecuencias
- Latencia mínima, UX premium y reducción masiva de peticiones inútiles al servidor.
- Requiere ejecutar Daphne en lugar de Gunicorn/uWSGI, y administrar un contenedor Redis dedicado a Channels.
