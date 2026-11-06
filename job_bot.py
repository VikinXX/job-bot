"""
Orquestador principal: coordina fetcher, scorer, database y notifier.
"""
import logging
from typing import List, Dict, Any
from config_loader import config
from job_fetcher import job_fetcher
from job_scorer import job_scorer
from database import db
from telegram_notifier import telegram_notifier

logger = logging.getLogger(__name__)


class JobBot:
    def __init__(self):
        self.min_score = config.get(("scoring", "min_score_to_notify"), 6)

    async def initialize(self):
        """Inicializa conexiones."""
        await db.connect()
        logger.info("Base de datos conectada")

        ok = await telegram_notifier.test_connection()
        if not ok:
            raise RuntimeError("No se pudo conectar con Telegram. Revisa token y chat_id.")

    async def run_once(self) -> Dict[str, Any]:
        """Ejecuta un ciclo completo de búsqueda."""
        stats = {
            "found": 0,
            "new": 0,
            "scored": 0,
            "notified": 0,
            "errors": 0,
        }

        logger.info("🔍 Iniciando búsqueda de ofertas...")

        # 1. Fetch ofertas
        try:
            jobs = await job_fetcher.search_all()
            stats["found"] = len(jobs)
            logger.info(f"Encontradas {len(jobs)} ofertas totales")
        except Exception as e:
            logger.error(f"Error en fetch: {e}")
            stats["errors"] += 1
            await telegram_notifier.send_error(f"Error fetching jobs: {e}")
            return stats

        # 2. Filtrar nuevas (no vistas)
        new_jobs = []
        for job in jobs:
            job_id = job.get("job_id", "")
            url = job.get("url", "")

            seen = await db.is_job_seen(job_id) or await db.is_url_seen(url)
            if not seen:
                new_jobs.append(job)

        stats["new"] = len(new_jobs)
        logger.info(f"Ofertas nuevas (no vistas): {len(new_jobs)}")

        if not new_jobs:
            await db.log_search(
                config.get(("search", "keywords"), []),
                config.get(("search", "locations"), []),
                stats["found"],
                0,
            )
            # Notificar que no hay ofertas nuevas
            await telegram_notifier.send_message(
                "🔍 <b>Búsqueda completada</b>\n\n"
                f"Se encontraron {stats['found']} ofertas totales, pero <b>ninguna es nueva</b> "
                f"(ya las habías visto en búsquedas anteriores)."
            )
            return stats

        # 3. Puntuar y notificar cada oferta nueva
        for job in new_jobs:
            try:
                # Scoring con IA
                score_data = await job_scorer.score_job(job)
                final_score = score_data.get("final_score", 0)
                stats["scored"] += 1

                # Guardar en BD
                await db.save_job(
                    job_id=job.get("job_id", ""),
                    source=job.get("source", "jsearch"),
                    title=job.get("title", ""),
                    company=job.get("company", ""),
                    location=job.get("location", ""),
                    url=job.get("url", ""),
                    score=final_score,
                    raw_data=job,
                )

                # Notificar si pasa umbral
                if final_score >= self.min_score:
                    sent = await telegram_notifier.send_job_alert(job, score_data)
                    if sent:
                        stats["notified"] += 1
                else:
                    logger.debug(f"Score {final_score} < {self.min_score}, no notifico: {job.get('title')}")

            except Exception as e:
                logger.error(f"Error procesando oferta {job.get('title')}: {e}")
                stats["errors"] += 1
                # Guardar aunque falle scoring
                await db.save_job(
                    job_id=job.get("job_id", ""),
                    source=job.get("source", "jsearch"),
                    title=job.get("title", ""),
                    company=job.get("company", ""),
                    location=job.get("location", ""),
                    url=job.get("url", ""),
                    score=None,
                    raw_data=job,
                )

        # 4. Log de búsqueda
        await db.log_search(
            config.get(("search", "keywords"), []),
            config.get(("search", "locations"), []),
            stats["found"],
            stats["new"],
            error=None if stats["errors"] == 0 else f"{stats['errors']} errores",
        )

        # Notificar si hay ofertas nuevas pero ninguna pasa el umbral
        if stats["new"] > 0 and stats["notified"] == 0:
            await telegram_notifier.send_message(
                "🔍 <b>Búsqueda completada</b>\n\n"
                f"Se encontraron {stats['new']} ofertas nuevas, pero <b>ninguna supera el umbral</b> "
                f"({self.min_score}/10).\n"
                f"Revisa los logs para ver los scores."
            )

        logger.info(f"✅ Ciclo completado: {stats}")
        return stats

    async def run_scheduled(self):
        """Ejecuta ciclo y envía resumen."""
        stats = await self.run_once()
        await telegram_notifier.send_summary(stats)

    async def shutdown(self):
        """Cierra conexiones."""
        await job_fetcher.close()
        await job_scorer.close()
        await db.close()
        logger.info("Bot apagado correctamente")


# Instancia global
job_bot = JobBot()