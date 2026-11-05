"""
Scorer de ofertas usando Groq API (gratis, modelos Llama/Mixtral rápidos).
Puntúa ofertas 1-10 según tu perfil profesional.
"""
import json
import logging
from typing import Dict, Any, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from config_loader import config

logger = logging.getLogger(__name__)


class JobScorer:
    def __init__(self):
        self.api_key = config.get(("api_keys", "groq_key"))
        self.model = config.get(("scoring", "model"), "llama-3.3-70b-versatile")
        self.temperature = config.get(("scoring", "temperature"), 0.1)
        self.max_tokens = config.get(("scoring", "max_tokens"), 500)
        self.weights = config.get(("scoring", "weights"), {})
        self.profile = config.get_section("profile")
        self.client = httpx.AsyncClient(
            base_url="https://api.groq.com/openai/v1",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    def _build_prompt(self, job: Dict[str, Any]) -> str:
        """Construye el prompt para la IA con el job y tu perfil."""
        profile = self.profile

        # Formatear skills
        core_skills = ", ".join(profile.get("core_skills", []))
        nice_skills = ", ".join(profile.get("nice_to_have_skills", []))
        dealbreakers = ", ".join(profile.get("dealbreakers", []))

        prefs = profile.get("preferences", {})

        return f"""
Eres un experto en reclutamiento técnico. Evalúa esta oferta de trabajo para un candidato específico y dale una puntuación del 1 al 10.

=== PERFIL DEL CANDIDATO ===
Rol objetivo: {profile.get('target_role', 'Software Engineer')}
Años experiencia: {profile.get('years_experience', 'N/A')}

Skills CORE (dominio fuerte):
{core_skills}

Skills NICE TO HAVE (bonus):
{nice_skills}

Dealbreakers (penalizan fuerte si aparecen):
{dealbreakers}

Preferencias:
- Remoto prioritario: {'Sí' if prefs.get('remote_first') else 'No'}
- Salario mínimo: {prefs.get('min_salary_eur', 'N/A')}€ bruto/año
- Salario máximo: {prefs.get('max_salary_eur', 'N/A')}€ bruto/año
- Inglés requerido: {'Sí' if prefs.get('english_required') else 'No'}
- Español requerido: {'Sí' if prefs.get('spanish_required') else 'No'}
- Sin visa: {'Sí' if not prefs.get('visa_sponsorship') else 'No - necesita visa'}
- Sin viajes: {'Sí' if prefs.get('no_travel') else 'No'}

Bio del candidato:
{profile.get('bio', 'No proporcionada')}

=== OFERTA DE TRABAJO ===
Título: {job.get('title', 'N/A')}
Empresa: {job.get('company', 'N/A')}
Ubicación: {job.get('location', 'N/A')}
Tipo: {job.get('job_type', 'N/A')}
Experiencia: {job.get('experience_level', 'N/A')}
Remoto: {'Sí' if job.get('is_remote') else 'No'}
Salario: {self._format_salary(job)}
Publicado: {job.get('posted_at', 'N/A')}

Descripción:
{job.get('description', 'Sin descripción')[:3000]}

Requisitos mencionados:
{', '.join(job.get('requirements', [])) if job.get('requirements') else 'No especificados'}

Beneficios:
{', '.join(job.get('benefits', [])) if job.get('benefits') else 'No especificados'}

=== INSTRUCCIONES DE PUNTUACIÓN ===
Evalúa cada dimensión (1-10 cada una) y calcula score ponderado:

1. SKILLS_MATCH (peso {self.weights.get('skills_match', 0.35)*100:.0f}%): Qué tan bien coinciden los requirements con core_skills. Penaliza dealbreakers.
2. EXPERIENCE_MATCH (peso {self.weights.get('experience_match', 0.20)*100:.0f}%): Nivel experiencia adecuado vs {profile.get('years_experience')} años.
3. SALARY_MATCH (peso {self.weights.get('salary_match', 0.15)*100:.0f}%): Salario en rango {prefs.get('min_salary_eur')}-{prefs.get('max_salary_eur')}€. Si no hay salario, score 5.
4. LOCATION_MATCH (peso {self.weights.get('location_match', 0.10)*100:.0f}%): Remoto/ubicación vs preferencias.
5. CULTURE_MATCH (peso {self.weights.get('culture_match', 0.10)*100:.0f}%): Stack moderno, buenas prácticas, testing, CI/CD, team culture.
6. GROWTH_POTENTIAL (peso {self.weights.get('growth_potential', 0.10)*100:.0f}%): Oportunidad aprender, crecer, responsabilidades.

=== FORMATO DE RESPUESTA (JSON estricto) ===
{{
  "scores": {{
    "skills_match": <1-10>,
    "experience_match": <1-10>,
    "salary_match": <1-10>,
    "location_match": <1-10>,
    "culture_match": <1-10>,
    "growth_potential": <1-10>
  }},
  "final_score": <1-10 con un decimal>,
  "reasoning": "Explicación breve (2-3 frases) de la puntuación final, mencionando puntos fuertes y débiles clave",
  "pros": ["punto fuerte 1", "punto fuerte 2"],
  "cons": ["punto débil 1", "punto débil 2"],
  "red_flags": ["alerta 1 si aplica"]
}}
"""

    def _format_salary(self, job: Dict) -> str:
        parts = []
        if job.get("salary_min"):
            parts.append(f"{job['salary_min']:,}")
        if job.get("salary_max"):
            parts.append(f"{job['salary_max']:,}")
        if parts:
            currency = job.get("salary_currency", "USD")
            period = job.get("salary_period", "YEAR")
            return f"{' - '.join(parts)} {currency}/{period}"
        return "No especificado"

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=15),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def score_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Puntúa una oferta usando Groq."""
        prompt = self._build_prompt(job)

        try:
            response = await self.client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "Eres un experto en reclutamiento técnico. Responde SOLO con JSON válido, sin markdown ni texto extra."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            result = json.loads(content)

            # Validar estructura
            if not self._validate_result(result):
                raise ValueError("Estructura de respuesta inválida")

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Error parseando JSON de Groq: {e}")
            return self._fallback_score(job)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("Rate limit en Groq")
            logger.error(f"Error HTTP Groq: {e.response.status_code} - {e.response.text}")
            return self._fallback_score(job)
        except Exception as e:
            logger.error(f"Error scoring job: {e}")
            return self._fallback_score(job)

    def _validate_result(self, result: Dict) -> bool:
        """Valida que la respuesta tenga la estructura esperada."""
        required_keys = ["scores", "final_score", "reasoning", "pros", "cons", "red_flags"]
        if not all(k in result for k in required_keys):
            return False

        scores = result["scores"]
        required_scores = ["skills_match", "experience_match", "salary_match",
                          "location_match", "culture_match", "growth_potential"]
        if not all(k in scores for k in required_scores):
            return False

        # Validar rangos
        for v in scores.values():
            if not isinstance(v, (int, float)) or v < 1 or v > 10:
                return False

        if not isinstance(result["final_score"], (int, float)) or result["final_score"] < 1 or result["final_score"] > 10:
            return False

        return True

    def _fallback_score(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Score básico si falla la IA."""
        return {
            "scores": {
                "skills_match": 5,
                "experience_match": 5,
                "salary_match": 5,
                "location_match": 5,
                "culture_match": 5,
                "growth_potential": 5,
            },
            "final_score": 5.0,
            "reasoning": "No se pudo evaluar con IA (error de API). Score neutral por defecto.",
            "pros": ["Evaluación automática no disponible"],
            "cons": ["Requiere revisión manual"],
            "red_flags": ["IA no disponible"],
        }

    async def close(self):
        await self.client.aclose()


# Instancia global
job_scorer = JobScorer()