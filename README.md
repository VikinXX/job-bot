# 🤖 LinkedIn Job Bot - Tu cazador de ofertas automático

Bot en Python que busca ofertas en LinkedIn/Indeed cada 30 min, las evalúa con IA (Groq gratis) según tu perfil, y te avisa por Telegram solo las que valen la pena (score ≥ 6/10).

## ✨ Características

| Feature | Descripción |
|---------|-------------|
| 🔍 **Búsqueda automática** | RapidAPI JSearch (LinkedIn + Indeed), 100 req/mes gratis |
| 🧠 **Scoring IA** | Groq (Llama 3.3 70B) - **gratis**, evalúa 6 dimensiones |
| 📱 **Telegram** | Alertas bonitas con score, pros/contras, link directo |
| 💾 **Anti-duplicados** | SQLite local, no te avisará 2 veces lo mismo |
| ⚙️ **Totalmente configurable** | Tu perfil, skills, salario, ubicación, dealbreakers... |
| 🐳 **Docker ready** | Despliega en cualquier VPS/servidor |

---

## 🚀 Instalación rápida (Windows)

### 1. Clona y entra
```bash
cd C:\Users\Usuario\linkedin-job-bot
```

### 2. Crea entorno virtual e instala
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Consigue tus API Keys (gratis)

| Servicio | Link | Qué necesitas |
|----------|------|---------------|
| **RapidAPI JSearch** | https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch | `X-RapidAPI-Key` (100 req/mes gratis) |
| **Groq** | https://console.groq.com/keys | API Key (gratis, rate limited) |
| **Telegram Bot** | Ver abajo | Token + Chat ID |

### 4. Crea tu Bot de Telegram

1. Abre Telegram → busca **@BotFather**
2. `/newbot` → nombre: `Mi Job Hunter` → username: `mi_job_hunter_bot`
3. **Copia el token** (ej: `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`)
4. Habla con tu bot → envía `/start`
5. Ve a: `https://api.telegram.org/bot<TOKEN>/getUpdates`
6. Busca `"chat":{"id":123456789}` → ese es tu **Chat ID**

### 5. Configura

```bash
# Opción A: Archivo local (recomendado)
copy config.local.yaml.example config.local.yaml
# Edita config.local.yaml con tus keys

# Opción B: Variables de entorno
copy .env.example .env
# Edita .env con tus keys
```

### 6. ¡Ejecuta!

```bash
python main.py
```

Deberías ver en Telegram: *"✅ Job Bot iniciado correctamente"* y la primera búsqueda.

---

## ⚙️ Personaliza tu perfil (LO MÁS IMPORTANTE)

Edita `config.yaml` o `config.local.yaml` sección **`profile`**:

```yaml
profile:
  target_role: "Senior Python Backend Developer"
  years_experience: 5

  core_skills:          # Lo que dominas (peso alto en score)
    - "Python"
    - "Django"
    - "FastAPI"
    - "PostgreSQL"
    - "Redis"
    - "Docker"
    - "Kubernetes"
    - "AWS"

  nice_to_have_skills:  # Bonus
    - "Go"
    - "TypeScript"
    - "Terraform"

  dealbreakers:         # Penalizan FUERTE si aparecen
    - "PHP"
    - "WordPress"
    - "Salesforce"
    - "legacy only"

  preferences:
    remote_first: true
    min_salary_eur: 45000
    max_salary_eur: 80000
    english_required: true
    no_travel: true
```

**Cuanto más específico seas, mejor filtra la IA.**

---

## 📊 Cómo funciona el scoring (1-10)

La IA evalúa 6 dimensiones con pesos configurables:

| Dimensión | Peso | Qué evalúa |
|-----------|------|------------|
| **Skills Match** | 35% | Coincidencia core_skills vs requirements, penaliza dealbreakers |
| **Experience Match** | 20% | Seniority adecuado vs tus años |
| **Salary Match** | 15% | Salario en tu rango (si no hay = 5) |
| **Location Match** | 10% | Remoto/ubicación vs preferencias |
| **Culture Match** | 10% | Stack moderno, testing, CI/CD, buenas prácticas |
| **Growth Potential** | 10% | Oportunidad aprender/crecer |

**Score final = suma ponderada** → Solo te avisa si ≥ `min_score_to_notify` (default 6).

---

## 🐳 Despliegue en servidor (VPS/Docker)

### Docker Compose
```yaml
# docker-compose.yml
version: '3.8'
services:
  job-bot:
    build: .
    restart: unless-stopped
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./config.local.yaml:/app/config.local.yaml:ro
    environment:
      - TZ=Europe/Madrid
```

```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

```bash
docker compose up -d
docker compose logs -f
```

### Systemd (Linux nativo)
```ini
# /etc/systemd/system/job-bot.service
[Unit]
Description=LinkedIn Job Bot
After=network.target

[Service]
Type=simple
User=tu_usuario
WorkingDirectory=/home/tu_usuario/linkedin-job-bot
ExecStart=/home/tu_usuario/linkedin-job-bot/venv/bin/python main.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now job-bot
sudo journalctl -u job-bot -f
```

---

## 📁 Estructura del proyecto

```
linkedin-job-bot/
├── main.py                 # Entry point + scheduler
├── config.yaml             # Plantilla configuración (versionada)
├── config.local.yaml       # TU config real (NO versionar)
├── config_loader.py        # Carga config con merge + env vars
├── requirements.txt
├── .gitignore
├── .env.example
│
├── job_fetcher.py          # RapidAPI JSearch client
├── job_scorer.py           # Groq IA scoring
├── database.py             # SQLite async (anti-duplicados)
├── telegram_notifier.py    # Bot Telegram con formato bonito
├── job_bot.py              # Orquestador principal
│
├── data/
│   └── jobs.db             # SQLite (auto-creado)
│
└── logs/
    └── bot.log             # Logs rotativos
```

---

## 🛠️ Comandos útiles

```bash
# Ver logs en tiempo real
tail -f logs/bot.log

# Ver stats de la BD
python -c "
import asyncio
from database import db
async def main():
    await db.connect()
    print(await db.get_stats())
asyncio.run(main())
"

# Test scoring manual
python -c "
import asyncio
from job_fetcher import job_fetcher
from job_scorer import job_scorer
async def test():
    jobs = await job_fetcher.search_keyword_location('Python Developer', 'Madrid')
    if jobs:
        score = await job_scorer.score_job(jobs[0])
        print(score)
asyncio.run(test())
"

# Una sola búsqueda manual (sin scheduler)
python -c "
import asyncio
from job_bot import job_bot
asyncio.run(job_bot.initialize())
asyncio.run(job_bot.run_scheduled())
"
```

---

## ❓ Troubleshooting

| Problema | Solución |
|----------|----------|
| `ModuleNotFoundError` | `venv\Scripts\activate` y `pip install -r requirements.txt` |
| `Error: Faltan configuraciones obligatorias` | Edita `config.local.yaml` o `.env` con tus keys |
| `Telegram: Unauthorized` | Token incorrecto o chat_id wrong |
| `RapidAPI 429` | Límite mensual alcanzado (100 gratis), espera o paga |
| `Groq 429` | Rate limit temporal, reintenta solo |
| `No llegan ofertas` | Amplia keywords/locations, baja `min_score_to_notify` |
| `Duplicados` | BD en `data/jobs.db` - borra para resetear |

---

## 💡 Tips para mejores resultados

1. **Keywords específicas**: `"Python Developer" "Django" "FastAPI"` > `"Developer"`
2. **Locations realistas**: Si buscas remoto en España → `["Spain", "Remote", "Madrid"]`
3. **Dealbreakers honestos**: Pon tecnologías que NO tocarías ni con un palo
4. **Salary realista**: Rango ancho (ej: 40k-80k) para no filtrar ofertas sin salario
5. **Revisa logs**: `logs/bot.log` te dice qué busca, qué encuentra, qué puntúa

---

## 📄 Licencia

MIT - Úsalo, modifícalo, compártelo.

---

**¿Dudas?** Revisa `logs/bot.log` o abre un issue. ¡A cazar ofertas! 🎯