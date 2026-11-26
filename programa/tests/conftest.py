import pytest

from buscador import config


@pytest.fixture(autouse=True)
def datos_aislados(tmp_path, monkeypatch):
    """Ningún test toca el índice ni la carpeta de resultados reales del programa."""
    monkeypatch.setattr(config, "DB", str(tmp_path / "indice_test.db"))
    monkeypatch.setattr(config, "SALIDAS", str(tmp_path / "Resultados"))
