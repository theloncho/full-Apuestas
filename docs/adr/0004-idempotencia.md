# ADR-0004: Idempotency keys en endpoints financieros

## Contexto
Redes inestables pueden causar reenvíos de requests. Sin idempotencia, un depósito o apuesta podría ejecutarse dos veces.

## Opciones
### A: Sin idempotencia (confiar en el frontend)
### B: Idempotency key en header/body + Redis cache

## Decisión
**Opción B**: Header `X-Idempotency-Key: <uuid>` con caché Redis TTL 24h. Si la key ya existe, se retorna la respuesta cacheada sin re-ejecutar.

## Consecuencias
- Operaciones financieras seguras ante reintentos
- Requiere Redis disponible
- El frontend debe generar y enviar UUID únicos

**Fecha**: 2026-05-26 | **Autor**: Equipo FairBet Lab
