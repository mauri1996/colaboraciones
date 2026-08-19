"""Arranque del bot de Telegram en el mismo loop de FastAPI."""

from __future__ import annotations

import logging

from telegram import BotCommand
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.bot.handlers import (
    cmd_anio,
    cmd_ayuda,
    cmd_cierre,
    cmd_exportar,
    cmd_gasto,
    cmd_grafico,
    cmd_mes,
    cmd_pagos,
    cmd_pendientes,
    cmd_soy,
    cmd_start,
    on_callback,
    on_message,
)
from app.config import get_settings

logger = logging.getLogger(__name__)


async def _post_init(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Ver tu ID y si estás en el hogar"),
            BotCommand("soy", "Vincularte: /soy Mauri o /soy Daysi"),
            BotCommand("gasto", "Registrar un gasto por texto"),
            BotCommand("mes", "Cuánto gastó el hogar este mes"),
            BotCommand("pagos", "Cuánto pagó cada uno"),
            BotCommand("anio", "Detalle mes a mes y resumen del año"),
            BotCommand("grafico", "Cuánto pagó cada uno y gastos por día"),
            BotCommand("cierre", "Cierre del mes"),
            BotCommand("exportar", "CSV del mes"),
            BotCommand("pendientes", "Gastos por confirmar"),
            BotCommand("ayuda", "Lista de comandos"),
            BotCommand("help", "Lista de comandos"),
        ]
    )
    me = await application.bot.get_me()
    logger.info("Bot de Telegram listo: @%s", me.username)


def build_application() -> Application:
    settings = get_settings()
    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .concurrent_updates(False)
        .post_init(_post_init)
        .build()
    )
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("soy", cmd_soy))
    application.add_handler(CommandHandler("gasto", cmd_gasto))
    application.add_handler(CommandHandler("mes", cmd_mes))
    application.add_handler(CommandHandler("pagos", cmd_pagos))
    application.add_handler(CommandHandler("balance", cmd_pagos))
    application.add_handler(CommandHandler("anio", cmd_anio))
    application.add_handler(CommandHandler("grafico", cmd_grafico))
    application.add_handler(CommandHandler("graph", cmd_grafico))
    application.add_handler(CommandHandler("cierre", cmd_cierre))
    application.add_handler(CommandHandler("exportar", cmd_exportar))
    application.add_handler(CommandHandler("pendientes", cmd_pendientes))
    application.add_handler(CommandHandler("ayuda", cmd_ayuda))
    application.add_handler(CommandHandler("help", cmd_ayuda))
    application.add_handler(CallbackQueryHandler(on_callback, pattern=r"^e:"))
    application.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.StatusUpdate.ALL, on_message)
    )
    return application


async def start_polling(application: Application) -> None:
    await application.initialize()
    await _post_init(application)
    await application.start()
    assert application.updater is not None
    await application.updater.start_polling(drop_pending_updates=True)
    logger.info("Polling de Telegram iniciado")


async def stop_polling(application: Application) -> None:
    if application.updater is not None:
        await application.updater.stop()
    await application.stop()
    await application.shutdown()
    logger.info("Bot de Telegram detenido")
