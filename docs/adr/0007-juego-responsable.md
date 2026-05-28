# ADR 0007: Controles de Juego Responsable

**Fecha:** 2026-05-27
**Estado:** Aceptado

## Contexto
La ley peruana (Ley 31557 / DS 005-2023-MINCETUR) exige medidas estrictas de juego responsable, incluyendo autoexclusión y límites de depósito.

## Opciones Consideradas
1. Implementar límites rígidos configurados únicamente por el administrador.
2. Permitir al usuario gestionar sus límites con periodos de enfriamiento (cooldown).

## Decisión
Se optó por la **Opción 2**. Bajar un límite será efectivo de inmediato. Subir un límite requerirá un "cooldown" de 24 horas para prevenir depósitos impulsivos. La autoexclusión (temporal o permanente) será irrevocable.

## Consecuencias
- Cumplimiento total de la normativa de MINCETUR.
- Mayor complejidad en la lógica de actualización del `GamblingLimit`, requiriendo campos de `pending_amount` y `pending_effective_at`.
