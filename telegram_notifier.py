"""
Notificador de Telegram para enviar ofertas puntuadas.
"""
import logging
from typing import Dict, Any, Optional
from telegram import Bot
from telegram.error import TelegramError
from config_loader import config

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self):
        self.bot_token = config.get(("telegram", "bot_token"))
        self.chat_id = config.get(("telegram", "chat_id"))
        self.bot = Bot(token=self.bot_token)
        self.min_score = config.get(("scoring", "min_score_to_notify"), 6)

    async def send_job_alert(self, job: Dict[str, Any], score_data: Dict[str, Any]) -> bool:
        """Envía una oferta que pasa el umbral mínimo."""
        final_score = score_data.get("final_score", 0)

        if final_score < self.min_score:
            logger.debug(f"Oferta '{job.get('title')}' score {final_score} < {self.min_score}, no notifico")
            return False

        message = self._format_message(job, score_data)

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            logger.info(f"✅ Enviado a Telegram: {job.get('title')} ({final_score}/10)")
            return True

        except TelegramError as e:
            logger.error(f"Error enviando a Telegram: {e}")
            return False

    def _format_message(self, job: Dict[str, Any], score_data: Dict[str, Any]) -> str:
        """Formatea el mensaje HTML para Telegram."""
        score = score_data.get("final_score", 0)
        scores = score_data.get("scores", {})
        reasoning = score_data.get("reasoning", "")
        pros = score_data.get("pros", [])
        cons = score_data.get("cons", [])
        red_flags = score_data.get("red_flags", [])

        # Emoji según score
        if score >= 8:
            emoji = "🟢"
        elif score >= 6:
            emoji = "🟡"
        else:
            emoji = "🔴"

        # Salario
        salary_str = self._format_salary(job)

        # Remoto
        remote_str = "🏠 Remoto" if job.get("is_remote") else "🏢 Presencial/Híbrido"

        lines = [
            f"{emoji} <b>Nueva oferta: {score}/10</b>",
            f"",
            f"<b>📋 {job.get('title', 'Sin título')}</b>",
            f"🏢 <b>Empresa:</b> {job.get('company', 'Desconocida')}",
            f"📍 <b>Ubicación:</b> {job.get('location', 'No especificada')} ({remote_str})",
            f"💰 <b>Salario:</b> {salary_str}",
            f"📅 <b>Publicado:</b> {self._format_date(job.get('posted_at'))}",
            f"",
            f"<b>📊 Desglose:</b>",
            f"  • Skills: {scores.get('skills_match', 'N/A')}/10",
            f"  • Experiencia: {scores.get('experience_match', 'N/A')}/10",
            f"  • Salario: {scores.get('salary_match', 'N/A')}/10",
            f"  • Ubicación: {scores.get('location_match', 'N/A')}/10",
            f"  • Cultura: {scores.get('culture_match', 'N/A')}/10",
            f"  • Crecimiento: {scores.get('growth_potential', 'N/A')}/10",
        ]

        if reasoning:
            lines.extend(["", f"<b>💭 Análisis:</b> {reasoning}"])

        if pros:
            lines.extend(["", "<b>✅ Pros:</b>"])
            for p in pros[:3]:
                lines.append(f"  • {p}")

        if cons:
            lines.extend(["", "<b>⚠️ Contras:</b>"])
            for c in cons[:3]:
                lines.append(f"  • {c}")

        if red_flags:
            lines.extend(["", "<b>🚨 Alertas:</b>"])
            for r in red_flags[:2]:
                lines.append(f"  • {r}")

        lines.extend(["", f"🔗 <a href='{job.get('url', '#')}'>Ver oferta en LinkedIn/Origen</a>"])

        return "\n".join(lines)

    def _format_salary(self, job: Dict) -> str:
        parts = []
        if job.get("salary_min"):
            parts.append(f"{job['salary_min']:,}")
        if job.get("salary_max"):
            parts.append(f"{job['salary_max']:,}")
        if parts:
            currency = job.get("salary_currency", "USD")
            period = job.get("salary_period", "YEAR")
            period_es = {"YEAR": "año", "MONTH": "mes", "HOUR": "hora"}.get(period, period)
            return f"{' - '.join(parts)} {currency}/{period_es}"
        return "No especificado"

    def _format_date(self, date_str: Optional[str]) -> str:
        if not date_str:
            return "Desconocida"
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return date_str[:16] if len(date_str) > 16 else date_str

    async def send_summary(self, stats: Dict[str, Any]):
        """Envía resumen de la búsqueda."""
        message = (
            f"📊 <b>Resumen de búsqueda</b>\n\n"
            f"🔍 Ofertas encontradas: {stats.get('found', 0)}\n"
            f"🆕 Ofertas nuevas: {stats.get('new', 0)}\n"
            f"📤 Notificaciones enviadas: {stats.get('notified', 0)}\n"
            f"⏱️ Próxima búsqueda en: {config.get(('scheduler', 'interval_minutes'), 30)} min"
        )
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode="HTML")
        except TelegramError as e:
            logger.error(f"Error enviando resumen: {e}")

    async def send_error(self, error: str):
        """Envía notificación de error crítico."""
        message = f"🚨 <b>Error en Job Bot</b>\n\n<code>{error}</code>"
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode="HTML")
        except TelegramError:
            pass  # Si falla Telegram, no podemos hacer nada

    async def test_connection(self) -> bool:
        """Prueba la conexión con Telegram."""
        try:
            me = await self.bot.get_me()
            logger.info(f"Bot conectado: @{me.username}")
            await self.bot.send_message(
                chat_id=self.chat_id,
                text="✅ <b>Job Bot iniciado correctamente</b>\n\n"
                     f"Buscaré ofertas cada {config.get(('scheduler', 'interval_minutes'), 30)} minutos.\n"
                     f"Umbral de notificación: {self.min_score}/10",
                parse_mode="HTML",
            )
            return True
        except TelegramError as e:
            logger.error(f"Error conectando con Telegram: {e}")
            return False


# Instancia global
telegram_notifier = TelegramNotifier()