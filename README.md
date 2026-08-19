# Contabilizador

Finanzas conjuntas de Mauri y Daysi: registrar compras y ver cuánto gastó el hogar y cada uno, mes a mes. No es un sistema de préstamos.

Panel: `http://127.0.0.1:7000` (o `WEB_PORT` en `.env`). Bot: [@mauri_daysi_compras_bot](https://t.me/mauri_daysi_compras_bot).

- Texto: `almuerzo 8.50` o `almuerzo 8.50 ayer`
- Foto o PDF de ticket/factura
- `/mes` `/pagos` `/anio` `/cierre` `/exportar` `/pendientes`
- Daysi: `/soy Daysi` cuando se una

Servidor: ver [docs/DEPLOY.md](docs/DEPLOY.md).

## Requisitos

- Python 3.12 o 3.13
- Token del bot (BotFather)
- API key de Gemini (opcional en fase 1; hay un valor de prueba)

## Arranque en Windows

En PowerShell, desde esta carpeta:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.main
```

Abre [http://127.0.0.1:7000](http://127.0.0.1:7000) (el puerto sale de `WEB_PORT` en `.env`).

Copia `.env.example` a `.env` y completa tokens. El archivo `.env` no se sube a git.

## Documentación para el agente

- [AGENTS.md](AGENTS.md)
- [docs/PRODUCT.md](docs/PRODUCT.md)
- [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md)
