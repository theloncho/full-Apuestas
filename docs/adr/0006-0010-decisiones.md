# ADR-0006: Política de re-cotización

## Contexto
Las cuotas pueden cambiar entre que el usuario abre el ticket y confirma la apuesta.

## Decisión
Si la cuota cambió, se muestra la nueva cuota y se exige reconfirmación explícita. El frontend compara `odds_confirmed` con `selection.odds` actual.

**Fecha**: 2026-05-26 | **Autor**: Equipo FairBet Lab

---

# ADR-0007: Controles de juego responsable

## Decisión
- Bajar límite de depósito: efectivo inmediatamente
- Subir límite: cooldown de 24 horas
- Autoexclusión temporal (7/30/90 días) o permanente: irrevocable antes del tiempo

**Fecha**: 2026-05-26 | **Autor**: Equipo FairBet Lab

---

# ADR-0008: Auditoría append-only con hash chain

## Decisión
Tabla `AuditLog` con `chain_hash = SHA256(previous_hash + payload)`. Protegida por reglas PostgreSQL contra UPDATE/DELETE. Endpoint de verificación de integridad.

**Fecha**: 2026-05-26 | **Autor**: Equipo FairBet Lab

---

# ADR-0009: Suspensión de mercado in-play

## Decisión
Evento crítico (gol, expulsión) → mercado suspendido 30 segundos via Celery task. Reactivación automática. Clientes notificados por WebSocket.

**Fecha**: 2026-05-26 | **Autor**: Equipo FairBet Lab

---

# ADR-0010: Django Channels vs Polling para odds en tiempo real

## Opciones
- A: Polling HTTP cada N segundos
- B: WebSocket con Django Channels + Redis

## Decisión
**Opción B**: WebSocket para latencia mínima. Canal por evento. El cliente recibe push updates sin polling.

**Fecha**: 2026-05-26 | **Autor**: Equipo FairBet Lab
