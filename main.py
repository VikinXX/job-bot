"""
Punto de entrada principal del bot.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config_loader import config
from job_bot import job_bot

# Configurar logging
log_level = config.get(("logging", "level"), "INFO")
log_file = config.get(("logging", "file"), "logs/bot.log")

Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

# Silenciar loggers ruidosos
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def main():
    logger.info("=" * 50)
    logger.info("🤖 Iniciando LinkedIn Job Bot")
    logger.info("=" * 50)

    try:
        # Inicializar bot
        await job_bot.initialize()

        # Ejecutar primera búsqueda si configurado
        if config.get(("scheduler", "run_on_start"), True):
            logger.info("🚀 Ejecutando búsqueda inicial...")
            await job_bot.run_scheduled()

        # Configurar scheduler
        interval_minutes = config.get(("scheduler", "interval_minutes"), 30)
        timezone = config.get(("scheduler", "timezone"), "Europe/Madrid")

        scheduler = AsyncIOScheduler(timezone=timezone)
        scheduler.add_job(
            job_bot.run_scheduled,
            IntervalTrigger(minutes=interval_minutes),
            id="job_search",
            name="Búsqueda programada de ofertas",
            replace_existing=True,
        )
        scheduler.start()

        logger.info(f"⏰ Scheduler iniciado: cada {interval_minutes} min (zona: {timezone})")
        logger.info("Bot corriendo. Presiona Ctrl+C para parar.")

        # Mantener vivo
        try:
            while True:
                await asyncio.sleep(60)
        except KeyboardInterrupt:
            logger.info("🛑 Señal de parada recibida")
        finally:
            scheduler.shutdown()
            await job_bot.shutdown()

    except Exception as e:
        logger.exception(f"Error fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Windows fix para asyncio
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Modo single-run para GitHub Actions
    if "GITHUB_ACTIONS" in os.environ:
        from job_bot import job_bot

        async def run_once():
            await job_bot.initialize()
            await job_bot.run_once()
            await job_bot.shutdown()

        asyncio.run(run_once())
    else:
        # Modo daemon normal (scheduler)
        asyncio.run(main())