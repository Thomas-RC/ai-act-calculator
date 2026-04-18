"""Konfiguracja aplikacji — wczytywana z env zgodnie z 12-factor.

Wartości defaultowe odpowiadają setupowi projektu (Paryż / EOG / Gemini Flash).
"""

from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


# Wszystkie regiony GCP fizycznie w Europejskim Obszarze Gospodarczym.
# Multi-region "eu" i globalne NIE są w tej liście — wymagamy konkretnego regionu EOG.
REGIONY_EOG: frozenset[str] = frozenset({
    "europe-west1",    # Saint-Ghislain, Belgia
    "europe-west3",    # Frankfurt, Niemcy
    "europe-west4",    # Eemshaven, Holandia
    "europe-west6",    # Zurich, Szwajcaria (technicznie EFTA — część EOG)
    "europe-west8",    # Mediolan, Włochy
    "europe-west9",    # Paryż, Francja (domyślne)
    "europe-west12",   # Turyn, Włochy
    "europe-north1",   # Hamina, Finlandia
    "europe-southwest1",  # Madryt, Hiszpania
    "europe-central2", # Warszawa, Polska
})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Vertex AI
    vertex_project_id: str = "vertex-wfirma-dev"
    vertex_location: str = "europe-west9"
    model_name: str = "gemini-2.5-flash"
    google_application_credentials: str = "/secrets/vertex-wfirma-dev-ea19981c2c30.json"

    # Korpus prawny
    legal_sources_dir: Path = Path(__file__).resolve().parent.parent / "legal_sources"
    legal_corpus_refresh_on_startup: bool = True
    legal_corpus_max_age_days: int = 30

    def validate_region_eog(self) -> None:
        if self.vertex_location not in REGIONY_EOG:
            raise RuntimeError(
                f"Region {self.vertex_location!r} NIE jest w EOG. "
                f"Dopuszczalne: {sorted(REGIONY_EOG)}"
            )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.validate_region_eog()
    return _settings
