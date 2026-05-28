# ADR-0002: Manejo de Decimal vs Float

## Contexto
Las operaciones financieras requieren precisión exacta. IEEE 754 float produce errores de redondeo (ej: 0.1 + 0.2 = 0.30000000000000004).

## Opciones consideradas

### Opción A: Float de Python/PostgreSQL
- **Pros**: Más rápido, más simple
- **Contras**: Errores de redondeo acumulativos, inconsistencias en montos

### Opción B: Decimal con precisión configurada
- **Pros**: Precisión exacta, cálculos financieros correctos
- **Contras**: Ligeramente más lento, más verbose

## Decisión
**Opción B**: `Decimal(max_digits=18, decimal_places=4)` en todos los campos monetarios. Precisión global configurada a 28 dígitos con redondeo `ROUND_HALF_UP`. **Prohibido** usar `float` en cualquier monto.

## Consecuencias
- payout = stake × odds siempre exacto
- Serialización requiere str() explícito en APIs JSON
- Todos los tests usan Decimal, nunca float

**Fecha**: 2026-05-26 | **Autor**: Equipo FairBet Lab
