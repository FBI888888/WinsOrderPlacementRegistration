from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantOwnedMixin, TimestampMixin


class ExportTemplate(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "export_templates"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    fields: Mapped[list] = mapped_column(JSON, nullable=False)
    filters: Mapped[dict | None] = mapped_column(JSON)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)


class ExportLog(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "export_logs"

    export_format: Mapped[str] = mapped_column(String(10), nullable=False)
    filters: Mapped[dict | None] = mapped_column(JSON)
    fields: Mapped[list] = mapped_column(JSON, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)