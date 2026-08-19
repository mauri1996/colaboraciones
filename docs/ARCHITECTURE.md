# Arquitectura

```text
Telegram grupo
    → bot (polling en local)
        → texto con monto → parser local
        → foto/PDF → Gemini Flash (Groq si 429)
        → expense status=pending_confirm
        → botones: Confirmar | Conjunto | Propio | Pagó Mauri | Pagó Daysi
        → al confirmar: status=confirmed

Navegador
    → FastAPI
        → mes y año: total hogar, cuánto pagó cada uno, categorías, IVA
        → editar / borrar
```

Un proceso Uvicorn. SQLite en `data/contabilizador.db`. Archivos en `data/inbox/`.

No hay módulo de préstamos ni deudas entre esposos.

## Providers LLM

`LLM_PROVIDER=gemini|groq` en `.env`. Interfaz única en `app/services/llm.py` (fase 4).

## Local vs servidor

| | Local (ahora) | Servidor (fase 9) |
|---|---|---|
| Arranque | `python -m app.main` | `docker compose up -d` |
| Bot | polling | polling (24/7) |
| Panel | `127.0.0.1:8000` | `0.0.0.0:8000` detrás del reverse proxy |
| Datos | `./data` | volumen Docker |
