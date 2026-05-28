# ADR 0009: Suspensión de Mercados In-Play

**Fecha:** 2026-05-27
**Estado:** Aceptado

## Contexto
Durante un evento en vivo ("in-play"), pueden ocurrir eventos críticos como un gol, penal o tarjeta roja. En estos momentos, las cuotas quedan temporalmente obsoletas y el riesgo para la casa es alto.

## Decisión
Se implementará un sistema de suspensión temporal mediante **Celery**. Ante un evento crítico, la tarea `suspend_market_temporarily` marcará `is_suspended=True` y programará una tarea `reactivate_market` con un retraso (countdown) de 30 segundos. Durante este periodo, las apuestas serán bloqueadas a nivel de validación.

## Consecuencias
- Mitigación del riesgo de "court-siding" o apuestas basadas en latencia de transmisión.
- Requiere infraestructura robusta de Celery y Redis para asegurar que la tarea de reactivación se ejecute a tiempo.
