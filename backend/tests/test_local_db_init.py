from pathlib import Path

import pytest

from scripts.init_local_db import build_database_url, validate_identifier, write_backend_env


def test_build_database_url_uses_local_credentials():
    url = build_database_url(
        host="localhost",
        port=3306,
        database="wins_order_book",
        user="root",
        password="ltx123589",
    )
    assert url == (
        "mysql+pymysql://root:ltx123589@localhost:3306/"
        "wins_order_book?charset=utf8mb4"
    )


def test_build_database_url_encodes_special_characters():
    url = build_database_url(
        host="localhost",
        port=3306,
        database="wins_order_book",
        user="test_user",
        password="p@ss/word",
    )
    assert "test_user:p%40ss%2Fword@localhost" in url


def test_identifier_rejects_sql_fragments():
    with pytest.raises(ValueError):
        validate_identifier("wins;DROP DATABASE mysql", "数据库名")


def test_write_backend_env_preserves_existing_secret(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("JWT_SECRET=existing-secret\n", encoding="utf-8")

    write_backend_env(
        env_path,
        host="localhost",
        port=3306,
        database="wins_order_book",
        user="root",
        password="ltx123589",
    )

    content = env_path.read_text(encoding="utf-8")
    assert "JWT_SECRET=existing-secret" in content
    assert "DATABASE_URL=mysql+pymysql://root:ltx123589@localhost:3306/wins_order_book" in content