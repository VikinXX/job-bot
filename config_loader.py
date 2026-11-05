"""
Cargador de configuración con soporte para:
- config.yaml (plantilla, sin secrets)
- config.local.yaml (tus valores reales, no versionado)
- Variables de entorno (prioridad más alta)
"""
import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
from dotenv import load_dotenv

# Cargar .env si existe
load_dotenv()


class Config:
    _instance: Optional["Config"] = None
    _data: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        base_dir = Path(__file__).parent

        # 1. Cargar config.yaml (plantilla)
        config_path = base_dir / "config.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}

        # 2. Sobreescribir con config.local.yaml (tus valores reales)
        local_path = base_dir / "config.local.yaml"
        if local_path.exists():
            with open(local_path, "r", encoding="utf-8") as f:
                local_data = yaml.safe_load(f) or {}
                self._deep_merge(self._data, local_data)

        # 3. Sobreescribir con variables de entorno (prioridad máxima)
        self._apply_env_overrides()

        # Validar obligatorios
        self._validate_required()

    def _deep_merge(self, base: Dict, override: Dict):
        """Merge recursivo de diccionarios."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _apply_env_overrides(self):
        """Aplica variables de entorno con prefijo JOB_BOT_"""
        env_mapping = {
            "JOB_BOT_RAPIDAPI_KEY": ("api_keys", "rapidapi_key"),
            "JOB_BOT_GROQ_KEY": ("api_keys", "groq_key"),
            "JOB_BOT_TELEGRAM_TOKEN": ("telegram", "bot_token"),
            "JOB_BOT_CHAT_ID": ("telegram", "chat_id"),
            "JOB_BOT_INTERVAL_MINUTES": ("scheduler", "interval_minutes"),
            "JOB_BOT_MIN_SCORE": ("scoring", "min_score_to_notify"),
        }

        for env_var, path in env_mapping.items():
            value = os.getenv(env_var)
            if value is not None:
                self._set_nested(path, self._convert_value(value))

    def _set_nested(self, path: tuple, value: Any):
        """Establece valor en ruta anidada."""
        current = self._data
        for key in path[:-1]:
            current = current.setdefault(key, {})
        current[path[-1]] = value

    def _convert_value(self, value: str) -> Any:
        """Convierte string a tipo apropiado."""
        # Booleanos
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False
        # Enteros
        try:
            return int(value)
        except ValueError:
            pass
        # Floats
        try:
            return float(value)
        except ValueError:
            pass
        return value

    def _validate_required(self):
        """Valida que los campos obligatorios estén presentes."""
        required = [
            ("api_keys", "rapidapi_key"),
            ("api_keys", "groq_key"),
            ("telegram", "bot_token"),
            ("telegram", "chat_id"),
        ]
        missing = []
        for path in required:
            value = self.get(path)
            if not value:
                missing.append(".".join(path))

        if missing:
            raise ValueError(
                f"Faltan configuraciones obligatorias: {', '.join(missing)}. "
                f"Edita config.local.yaml o define variables de entorno."
            )

    def get(self, path: tuple, default: Any = None) -> Any:
        """Obtiene valor por ruta (tupla de claves)."""
        current = self._data
        for key in path:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return default
            if current is None:
                return default
        return current

    def get_section(self, section: str) -> Dict[str, Any]:
        """Obtiene una sección completa."""
        return self._data.get(section, {})

    @property
    def all(self) -> Dict[str, Any]:
        return self._data.copy()


# Instancia global
config = Config()