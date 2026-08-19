# Plan de implementación

No pases de fase sin cumplir el DoD. Cada fase corre en local con `python -m app.main`.

## Fase 1 — Esqueleto (hecha)

Repo, config, SQLite, Alembic, página de estado, `.env.example`.

**DoD:** Uvicorn levanta y en `http://127.0.0.1:8000` se ve “Contabilizador OK”. La base existe y responde.

## Fase 2 — Personas y permisos (hecha)

Seed de las dos personas. Solo esos Telegram IDs pueden hablarle al bot.

**DoD:** un ID no autorizado recibe “no estás en el hogar”.

## Fase 3 — Gastos por texto (hecha)

Parser `almuerzo 8.50`. Botones de confirmación. Funciona con un solo miembro (Mauri); Daysi se vincula después con `/soy Daysi`.

Parser `almuerzo 8.50`. Botones de confirmación.

**DoD:** un texto queda en SQLite como `confirmed` tras pulsar Confirmar.

## Fase 4 — Fotos y PDFs (hecha)

## Fase 5 — Facturas (hecha)

## Fase 6 — Pareja (hecha)

## Fase 7 — Panel web (hecha)

## Fase 8 — Recuento mensual (hecha)

## Fase 9 — Servidor (hecha)

Dockerfile + compose + [docs/DEPLOY.md](DEPLOY.md). Finanzas conjuntas: recuento por persona y por mes, sin deudas.

**DoD:** `docker compose up -d` en el servidor; bot y panel vivos.

## Fase 10 — Uso diario (hecha)

Pendientes, corregir monto sin cancelar el registro, aviso si ya hay un gasto confirmado el mismo día por el mismo monto, y clave opcional del panel (`PANEL_USER` / `PANEL_PASSWORD`; vacía = abierto en local). En el panel se puede editar el monto.

**DoD:** `/pendientes` lista lo no confirmado. Corregir + `8.50` actualiza el monto y vuelve a pedir confirmación. `/health` sigue sin clave.

## Fase 11 — Fecha y edición (hecha)

Fecha en el texto (`ayer`, `15/08`, `15 de agosto`), cancelar un pendiente, corregir fecha o monto, y ver/confirmar pendientes en el panel. El recuento usa `spent_on`.

**DoD:** `almuerzo 8.50 ayer` queda en el día anterior. Cancelar no guarda el gasto. El panel muestra por confirmar y deja cambiar la fecha.
