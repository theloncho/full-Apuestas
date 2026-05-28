# ADR-0003: Estrategia de concurrencia — select_for_update

## Contexto
Múltiples usuarios pueden apostar simultáneamente. Sin control de concurrencia, es posible el "doble gasto" (apostar más fichas de las disponibles).

## Opciones
### A: Bloqueo optimista (versioning)
- Pros: Menor contención, mejor throughput
- Contras: Requiere reintentos, más complejo

### B: Bloqueo pesimista (select_for_update)
- Pros: Garantía absoluta, simple de implementar
- Contras: Mayor contención bajo carga alta

## Decisión
**Opción B**: `select_for_update()` en todo movimiento de wallet dentro de `transaction.atomic()`. La integridad financiera es prioritaria sobre el throughput.

## Consecuencias
- Cero doble gasto bajo cualquier nivel de concurrencia
- Posible bottleneck con muchas apuestas simultáneas al mismo usuario
- Mitigable con connection pooling y timeouts

**Fecha**: 2026-05-26 | **Autor**: Equipo FairBet Lab
