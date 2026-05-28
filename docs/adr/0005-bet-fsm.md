# ADR-0005: Máquina de estados de Bet (django-fsm)

## Contexto
Una apuesta tiene un ciclo de vida complejo con transiciones que deben ser controladas.

## Opciones
### A: CharField simple con validación manual
### B: django-fsm con decorador @transition

## Decisión
**Opción B**: `django-fsm` con `FSMField`. Estados: `pending → accepted → settling → won|lost|void|cashed_out → settled`. Cada transición dispara operaciones de wallet atómicas.

Estados terminales (`settled`) son irrevocables.

## Consecuencias
- Transiciones inválidas son bloqueadas por el framework
- Cada transición es un punto de integración con wallet y audit
- Testing directo de la FSM

**Fecha**: 2026-05-26 | **Autor**: Equipo FairBet Lab
