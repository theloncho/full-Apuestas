# ADR-0001: Modelo de partida doble para el wallet

## Contexto

El sistema necesita un wallet que garantice integridad financiera absoluta. Los enfoques comunes son:
- Campo `balance` en el modelo de usuario (simple pero propenso a inconsistencias)
- Partida doble (double-entry bookkeeping) con ledger entries

## Opciones consideradas

### Opción A: Campo balance en User
- **Pros**: Simple de implementar, queries rápidas
- **Contras**: No hay trazabilidad, posible inconsistencia por concurrencia, no se puede reconstruir historial

### Opción B: Partida doble con LedgerEntry
- **Pros**: Trazabilidad completa, saldo siempre derivado, cada operación es auditable, suma global = 0
- **Contras**: Más queries para calcular saldo, mayor complejidad

## Decisión

**Opción B: Partida doble.** Cada operación financiera crea mínimo 2 `LedgerEntry` (débito + crédito) cuya suma siempre es cero. El saldo NUNCA se almacena; siempre se calcula por `SUM(credits) - SUM(debits)`.

Cuentas definidas: `wallet_usuario`, `casa`, `apuestas_pendientes`, `bonos`.

## Consecuencias

- **Más fácil**: Auditoría, debugging financiero, reconstrucción de estados
- **Más difícil**: Performance en saldo (mitigado con índices)
- **Deuda técnica**: Podrían necesitarse snapshots periódicos si el volumen crece mucho

**Fecha**: 2026-05-26
**Autor**: Equipo FairBet Lab
