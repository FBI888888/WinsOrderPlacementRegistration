from sqlalchemy.engine import make_url
import pymysql

from app.core.config import get_settings
from scripts.init_local_db import validate_identifier


def ensure_database(database_url: str) -> str:
    url = make_url(database_url)
    if not url.drivername.startswith("mysql+"):
        raise ValueError("DATABASE_URL 必须是 MySQL 连接")
    database = validate_identifier(url.database or "", "数据库名")
    connection = pymysql.connect(
        host=url.host or "localhost",
        port=url.port or 3306,
        user=url.username or "",
        password=url.password or "",
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=8,
        read_timeout=10,
        write_timeout=10,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        connection.close()

    verification = pymysql.connect(
        host=url.host or "localhost",
        port=url.port or 3306,
        user=url.username or "",
        password=url.password or "",
        database=database,
        charset="utf8mb4",
        connect_timeout=8,
    )
    try:
        with verification.cursor() as cursor:
            cursor.execute("SELECT DATABASE()")
            selected_database = cursor.fetchone()[0]
            if selected_database != database:
                raise RuntimeError("远程数据库连接验证失败")
    finally:
        verification.close()
    return database


def main() -> None:
    settings = get_settings()
    try:
        database = ensure_database(settings.database_url)
    except (pymysql.MySQLError, ValueError, RuntimeError) as exc:
        raise SystemExit(f"远程数据库初始化失败：{exc}") from exc
    print(f"数据库 {database} 已创建并验证连接")


if __name__ == "__main__":
    main()