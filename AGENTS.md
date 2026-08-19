# Contabilizador — instrucciones para el agente

Finanzas conjuntas de un matrimonio (Mauri y Daysi). El bot registra compras y gastos del hogar. No es un sistema de préstamos ni de “quién le debe a quién”.

- Bot de Telegram para texto, fotos y PDFs
- Extracción con LLM (gastos + facturas Ecuador: RUC/IVA)
- Confirmación en Telegram antes de guardar
- SQLite como fuente de verdad
- Panel web para ver cuánto gastó el hogar, cuánto pagó cada uno, mes a mes y en el año

## Stack obligatorio (no cambiar sin preguntar)

- Python 3.12+ (el PC local usa 3.13)
- python-telegram-bot v21+ (polling)
- FastAPI + Jinja2 (un solo proceso, sin frontend Node)
- SQLite + SQLAlchemy 2 + Alembic
- Pydantic v2 para config y schema de extracción
- LLM gratis: Gemini Flash por defecto, Groq como respaldo
- Textos con monto se parsean en local; el LLM solo corre para fotos/PDF

## Producto (no negociable)

- Son esposos: caja conjunta. Nunca muestres deudas, saldos a deber, ni “le debe a”.
- `paid_by` = quién pagó (para ver cuánto gastó cada uno), no un crédito.
- `shared` = gasto conjunto del hogar. `personal` = gasto propio de esa persona. Ambos suman al total del hogar.
- El recuento responde: ¿cuánto gastamos juntos? ¿cuánto pagó Mauri? ¿cuánto pagó Daysi? ¿en este mes y a lo largo de los meses?

## Entorno

- Desarrollo: Windows, `python -m app.main` → puerto de `WEB_PORT` (ahora 7000)
- Producción: mismo repo en el servidor (Docker Compose, fase 9)
- Secretos solo en `.env`

## Reglas

- Español en UI, bot y categorías
- USD, timezone America/Guayaquil
- Nunca guardar un gasto sin confirmación
- Solo IDs del hogar pueden registrar
- No lenguaje de préstamos / Splitwise / deudas de pareja

## Comandos

- `/gasto` — registro manual
- `/mes` — cuánto gastó el hogar este mes
- `/pagos` y `/balance` — cuánto pagó cada uno (no deudas)
- `/anio` — detalle de cada mes y resumen del año
- `/grafico` o `/graph` — barras del total pagado por cada uno y línea diaria del mes
- `/cierre` — cierre del mes
- `/exportar` — CSV
- `/pendientes` — gastos por confirmar
- `/ayuda` o `/help` — lista de comandos
- Fecha: `ayer`, `15/08` o `15 de agosto` en el texto
