from sqlalchemy import create_engine, text

from scripts.prepare_production_db import (
    BUSINESS_TABLES,
    clear_business_data,
    convert_owner,
    load_owner,
    table_counts,
    validate_identity,
    verify_result,
)


def create_database():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE users ("
                "id INTEGER PRIMARY KEY, email TEXT, name TEXT, password_hash TEXT, is_active BOOLEAN)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE tenants ("
                "id INTEGER PRIMARY KEY, name TEXT, is_active BOOLEAN)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE members ("
                "id INTEGER PRIMARY KEY, user_id INTEGER, tenant_id INTEGER, role TEXT, "
                "is_active BOOLEAN)"
            )
        )
        for table in BUSINESS_TABLES:
            extra_column = ", reversed_entry_id INTEGER" if table == "ledger_entries" else ""
            connection.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY{extra_column})"))
        connection.execute(
            text(
                "INSERT INTO users VALUES "
                "(1, 'demo@example.com', '演示负责人', 'old-hash', TRUE)"
            )
        )
        connection.execute(text("INSERT INTO tenants VALUES (1, '演示账套', TRUE)"))
        connection.execute(text("INSERT INTO members VALUES (1, 1, 1, 'OWNER', TRUE)"))
        for table in BUSINESS_TABLES:
            connection.execute(text(f"INSERT INTO {table} (id) VALUES (1)"))
    return engine


def test_prepare_production_database_keeps_only_converted_owner():
    test_engine = create_database()
    password = "temporary-strong-password"

    with test_engine.begin() as connection:
        owner = load_owner(connection)
        clear_business_data(connection)
        convert_owner(
            connection,
            owner=owner,
            email="owner@example.com",
            admin_name="正式管理员",
            tenant_name="正式账套",
            password=password,
        )
        verify_result(connection, email="owner@example.com", password=password)

        assert table_counts(connection, BUSINESS_TABLES) == {
            table: 0 for table in BUSINESS_TABLES
        }
        converted = load_owner(connection)
        assert converted.email == "owner@example.com"
        assert converted.name == "正式管理员"
        assert converted.tenant_name == "正式账套"


def test_validate_identity_normalizes_values():
    assert validate_identity(
        email="OWNER@EXAMPLE.COM",
        admin_name="  正式管理员  ",
        tenant_name="  正式账套  ",
    ) == ("owner@example.com", "正式管理员", "正式账套")