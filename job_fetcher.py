"""
Fetcher de ofertas usando RapidAPI JSearch (LinkedIn, Indeed, etc.)
Plan gratis: 100 requests/mes en RapidAPI
"""
import httpx
import logging
from typing import List, Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from config_loader import config

logger = logging.getLogger(__name__)


class JobFetcher:
    BASE_URL = "https://jsearch.p.rapidapi.com/search"

    def __init__(self):
        self.api_key = config.get(("api_keys", "rapidapi_key"))
        self.headers = {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }
        self.client = httpx.AsyncClient(timeout=30.0, headers=self.headers)
        self.search_config = config.get_section("search")

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def _make_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Hace request con reintentos automáticos."""
        response = await self.client.get(self.BASE_URL, params=params)
        response.raise_for_status()
        return response.json()

    def _build_query(self, keyword: str, location: str, page: int = 1) -> Dict[str, Any]:
        """Construye parámetros de búsqueda."""
        params = {
            "query": f"{keyword} {location}".strip(),
            "page": str(page),
            "num_pages": "1",
        }

        # Filtros opcionales
        if self.search_config.get("job_type"):
            params["employment_types"] = self.search_config["job_type"]

        if self.search_config.get("experience_level"):
            params["experience_levels"] = self.search_config["experience_level"]

        if self.search_config.get("remote_filter"):
            params["remote_jobs_only"] = "true" if self.search_config["remote_filter"] == "remote" else "false"

        if self.search_config.get("date_posted"):
            date_map = {
                "today": "today",
                "3days": "3days",
                "week": "week",
                "month": "month",
            }
            params["date_posted"] = date_map.get(self.search_config["date_posted"], "month")

        return params

    def _normalize_job(self, raw: Dict[str, Any], source: str = "jsearch") -> Dict[str, Any]:
        """Normaliza campos de la API a formato interno."""
        # JSearch devuelve campos específicos
        return {
            "job_id": f"{source}_{raw.get('job_id', '')}",
            "source": source,
            "title": raw.get("job_title", ""),
            "company": raw.get("employer_name", ""),
            "location": self._format_location(raw),
            "url": raw.get("job_apply_link") or raw.get("job_google_link", ""),
            "description": raw.get("job_description", ""),
            "salary_min": raw.get("job_min_salary"),
            "salary_max": raw.get("job_max_salary"),
            "salary_currency": raw.get("job_salary_currency", "USD"),
            "salary_period": raw.get("job_salary_period", "YEAR"),
            "job_type": raw.get("job_employment_type", ""),
            "experience_level": raw.get("job_experience_level", ""),
            "is_remote": raw.get("job_is_remote", False),
            "posted_at": raw.get("job_posted_at_datetime_utc"),
            "benefits": raw.get("job_benefits", []),
            "requirements": raw.get("job_required_skills", []),
            "raw_data": raw,
        }

    def _format_location(self, raw: Dict) -> str:
        parts = []
        for field in ["job_city", "job_state", "job_country"]:
            if raw.get(field):
                parts.append(raw[field])
        return ", ".join(parts) if parts else "Ubicación no especificada"

    async def search_keyword_location(self, keyword: str, location: str) -> List[Dict[str, Any]]:
        """Busca ofertas para una combinación keyword+location."""
        all_jobs = []
        pages = self.search_config.get("pages_per_search", 2)

        for page in range(1, pages + 1):
            try:
                params = self._build_query(keyword, location, page)
                data = await self._make_request(params)

                jobs = data.get("data", [])
                if not jobs:
                    break

                for job in jobs:
                    normalized = self._normalize_job(job)
                    all_jobs.append(normalized)

                logger.info(f"Página {page}: {len(jobs)} ofertas para '{keyword}' en '{location}'")

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning("Rate limit alcanzado en RapidAPI")
                    break
                logger.error(f"Error HTTP {e.response.status_code}: {e.response.text}")
                break
            except Exception as e:
                logger.error(f"Error buscando '{keyword}' en '{location}': {e}")
                break

        return all_jobs

    async def search_all(self) -> List[Dict[str, Any]]:
        """Ejecuta todas las combinaciones de keywords x locations."""
        keywords = self.search_config.get("keywords", ["Python Developer"])
        locations = self.search_config.get("locations", ["Remote"])

        all_jobs = []
        seen_urls = set()

        for keyword in keywords:
            for location in locations:
                jobs = await self.search_keyword_location(keyword, location)

                # Deduplicar por URL
                for job in jobs:
                    url = job.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_jobs.append(job)

        logger.info(f"Total ofertas únicas encontradas: {len(all_jobs)}")
        return all_jobs

    async def close(self):
        await self.client.aclose()


# Instancia global
job_fetcher = JobFetcher()