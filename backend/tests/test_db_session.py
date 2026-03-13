from app.db.session import _normalize_database_url


def test_postgres_url_keeps_psycopg2_when_driver_is_present(monkeypatch):
    monkeypatch.setattr("app.db.session._module_available", lambda name: name == "psycopg2")
    url = _normalize_database_url("postgresql+psycopg2://u:p@127.0.0.1:5432/db")
    assert url.startswith("postgresql+psycopg2://")


def test_postgres_url_falls_back_to_psycopg_v3_when_psycopg2_is_missing(monkeypatch):
    monkeypatch.setattr("app.db.session._module_available", lambda name: name == "psycopg")
    url = _normalize_database_url("postgresql+psycopg2://u:p@127.0.0.1:5432/db")
    assert url.startswith("postgresql+psycopg://")


def test_plain_postgres_url_gets_explicit_driver(monkeypatch):
    monkeypatch.setattr("app.db.session._module_available", lambda name: name == "psycopg")
    url = _normalize_database_url("postgresql://u:p@127.0.0.1:5432/db")
    assert url.startswith("postgresql+psycopg://")
