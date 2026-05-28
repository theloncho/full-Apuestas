# FairBet Lab ⚽

Plataforma educativa de apuestas deportivas con moneda virtual.

> **Plataforma educativa con moneda virtual. No constituye una casa de apuestas.**
> Conforme a la Ley 31557 y DS 005-2023-MINCETUR.

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Backend | Django 5.1 + DRF |
| Base de datos | PostgreSQL 15 |
| Frontend | HTML5 + Bootstrap 5 + Alpine.js |
| Tiempo real | Django Channels + Redis |
| Tareas async | Celery + Redis |
| Despliegue | Docker + Docker Compose |

## Inicio rápido

```bash
# 1. Clonar y entrar al directorio
cd fairbet/

# 2. Levantar con Docker
docker-compose up --build

# 3. En otra terminal, cargar datos de prueba
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py seed_data

# 4. Acceder
# App: http://localhost:8000
# Admin: http://localhost:8000/admin/
# API Docs: http://localhost:8000/api/docs/
```

## Usuarios de prueba

| Usuario | Contraseña | Rol |
|---------|-----------|-----|
| jugador1 | Test1234! | Usuario verificado (500 fichas) |
| jugador2 | Test1234! | Usuario verificado (500 fichas) |
| jugador3 | Test1234! | Usuario verificado (500 fichas) |
| admin | Admin1234! | Superusuario |

## Funcionalidades

### Nivel 1 — Núcleo (55%)
- ✅ Registro con KYC simulado (DNI peruano + edad ≥ 18)
- ✅ Wallet con partida doble (saldo por SUM, nunca almacenado)
- ✅ Catálogo de eventos con mercados 1X2, Over/Under, BTTS
- ✅ Apuesta simple con FSM completa
- ✅ Controles de juego responsable (límites + autoexclusión)

### Nivel 2 — Avanzado (25%)
- ✅ Cuotas en tiempo real (Django Channels WebSocket)
- ✅ Re-cotización al cambiar odds
- ✅ Apuestas en vivo (in-play) con suspensión de mercado
- ✅ Cash-out anticipado

### Nivel 3 — Compliance (20%)
- ✅ Auditoría inmutable con hash chain SHA-256
- ✅ Anti-fraude (misma IP, patrones idénticos, deposit+cashout)
- ✅ Dashboard del operador (GGR, exposición, alertas)
- ✅ Reporte CSV estilo MINCETUR

### UI / UX (Mejoras Recientes)
- ✅ Diseño Premium Dark Mode con paleta de colores inmersiva.
- ✅ Filtrado dinámico de eventos (En Vivo / Próximos) utilizando Alpine.js sin recargar la página.
- ✅ Alertas y notificaciones del sistema con auto-desvanecimiento (auto-dismiss).
- ✅ Tablas de datos integradas al modo oscuro en paneles administrativos y de usuario.

## Tests

```bash
# Ejecutar tests
docker-compose exec web python -m pytest -v

# Con cobertura
docker-compose exec web python -m pytest --cov=apps/wallet --cov=apps/betting --cov-report=term-missing
```

## Estructura del proyecto

```
fairbet/
├── config/          # Configuración Django, ASGI, Celery
├── apps/
│   ├── users/       # KYC, estados, juego responsable
│   ├── wallet/      # Partida doble, LedgerEntry
│   ├── betting/     # FSM de apuestas, liquidación
│   ├── odds/        # WebSocket, Celery tasks
│   ├── audit/       # Hash chain inmutable
│   ├── fraud/       # Detección anti-fraude
│   └── dashboard/   # Métricas operador
├── templates/       # Bootstrap 5 + Alpine.js
├── static/          # CSS design system
├── docs/            # ADRs, sketches, bitácoras
└── docker-compose.yml
```

## Licencia

Proyecto educativo — Universidad, Taller de Lenguajes de Programación.
