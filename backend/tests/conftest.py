from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.db.session import get_db
from app.main import app

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def override_get_db() -> Generator[Session, None, None]:
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def register(client: TestClient, *, email: str, tenant_name: str = "测试账套") -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "tenant_name": tenant_name,
            "name": "负责人",
            "email": email,
            "password": "password123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    token = register(client, email="owner@example.com")
    return {"Authorization": f"Bearer {token}"}