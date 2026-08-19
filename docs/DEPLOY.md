# Despliegue en el servidor (fase 9)

El bot necesita un proceso 24/7. En el servidor:

1. Copia el repo y el `.env` (nunca lo subas a git).
2. En `.env` pon `WEB_HOST=0.0.0.0` y el puerto que vaya a exponer.
3. Arranque:

```bash
docker compose up -d --build
```

El panel queda en el puerto 8000 del compose. La base y las fotos viven en `./data`.

Sin Docker:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m alembic upgrade head
WEB_HOST=0.0.0.0 WEB_PORT=8000 .venv/bin/python -m app.main
```

Solo debe haber **un** proceso del bot. Dos instancias generan `Conflict` en Telegram.

Si el panel queda expuesto, pon `PANEL_USER` y `PANEL_PASSWORD` en `.env`. Con la clave vacía el panel queda abierto (así está en local). `/health` no pide clave.
