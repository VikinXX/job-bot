"""
Base de datos SQLite asíncrona para guardar ofertas ya vistas
y evitar notificaciones duplicadas.
"""
import aiosqlite
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
from config_loader import config


class JobDatabase:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = config.get(("database", "path"), "data/jobs.db")
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self):
        """Inicializa la conexión y crea tablas."""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._create_tables()

    async def _create_tables(self):
        """Crea las tablas si no existen."""
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS seen_jobs (
                job_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT,
                url TEXT UNIQUE NOT NULL,
                score REAL,
                scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                raw_data TEXT
            );

            CREATE TABLE IF NOT EXISTS search_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                keywords TEXT,
                locations TEXT,
                results_count INTEGER,
                new_jobs_count INTEGER,
                error TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_seen_jobs_url ON seen_jobs(url);
            CREATE INDEX IF NOT EXISTS idx_seen_jobs_scored_at ON seen_jobs(scored_at);
        """)
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    async def is_job_seen(self, job_id: str) -> bool:
        """Verifica si ya procesamos esta oferta."""
        cursor = await self._db.execute(
            "SELECT 1 FROM seen_jobs WHERE job_id = ?", (job_id,)
        )
        return await cursor.fetchone() is not None

    async def is_url_seen(self, url: str) -> bool:
        """Verifica si ya procesamos esta URL (backup)."""
        cursor = await self._db.execute(
            "SELECT 1 FROM seen_jobs WHERE url = ?", (url,)
        )
        return await cursor.fetchone() is not None

    async def save_job(
        self,
        job_id: str,
        source: str,
        title: str,
        company: str,
        location: str,
        url: str,
        score: Optional[float] = None,
        raw_data: Optional[Dict] = None,
    ):
        """Guarda una oferta procesada."""
        await self._db.execute(
            """
            INSERT OR REPLACE INTO seen_jobs
            (job_id, source, title, company, location, url, score, raw_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                source,
                title,
                company,
                location,
                url,
                score,
                json.dumps(raw_data, ensure_ascii=False) if raw_data else None,
            ),
        )
        await self._db.commit()

    async def log_search(
        self,
        keywords: List[str],
        locations: List[str],
        results_count: int,
        new_jobs_count: int,
        error: Optional[str] = None,
    ):
        """Registra una búsqueda para auditoría."""
        await self._db.execute(
            """
            INSERT INTO search_log (keywords, locations, results_count, new_jobs_count, error)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                json.dumps(keywords, ensure_ascii=False),
                json.dumps(locations, ensure_ascii=False),
                results_count,
                new_jobs_count,
                error,
            ),
        )
        await self._db.commit()

    async def get_recent_jobs(self, limit: int = 50) -> List[Dict]:
        """Obtiene ofertas recientes para debug."""
        cursor = await self._db.execute(
            """
            SELECT job_id, source, title, company, location, url, score, scored_at
            FROM seen_jobs
            ORDER BY scored_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_stats(self) -> Dict[str, Any]:
        """Estadísticas de la base de datos."""
        cursor = await self._db.execute("SELECT COUNT(*) as total FROM seen_jobs")
        total = (await cursor.fetchone())["total"]

        cursor = await self._db.execute(
            "SELECT COUNT(*) as scored FROM seen_jobs WHERE score IS NOT NULL"
        )
        scored = (await cursor.fetchone())["scored"]

        cursor = await self._db.execute(
            "SELECT AVG(score) as avg_score FROM seen_jobs WHERE score IS NOT NULL"
        )
        avg_score = (await cursor.fetchone())["avg_score"]

        cursor = await self._db.execute(
            "SELECT COUNT(*) as searches FROM search_log"
        )
        searches = (await cursor.fetchone())["searches"]

        return {
            "total_jobs": total,
            "scored_jobs": scored,
            "avg_score": round(avg_score, 2) if avg_score else 0,
            "total_searches": searches,
        }


# Instancia global
db = JobDatabase()