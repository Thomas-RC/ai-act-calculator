"""Testy konfiguracji — weryfikacja EOG i defaultów."""

import pytest

from config import Settings, REGIONY_EOG


def test_region_europe_west9_jest_eog():
    s = Settings(vertex_location="europe-west9")
    s.validate_region_eog()  # nie powinno rzucić


def test_region_us_jest_odrzucany():
    s = Settings(vertex_location="us-central1")
    with pytest.raises(RuntimeError) as exc:
        s.validate_region_eog()
    assert "NIE jest w EOG" in str(exc.value)


def test_region_multi_region_eu_jest_odrzucany():
    """multi-region 'eu' może routować na endpointy spoza EOG — wymagamy konkretnego."""
    s = Settings(vertex_location="eu")
    with pytest.raises(RuntimeError):
        s.validate_region_eog()


def test_region_global_jest_odrzucany():
    s = Settings(vertex_location="global")
    with pytest.raises(RuntimeError):
        s.validate_region_eog()


def test_warszawa_jest_eog():
    s = Settings(vertex_location="europe-central2")
    s.validate_region_eog()


def test_default_location():
    s = Settings()
    assert s.vertex_location in REGIONY_EOG
