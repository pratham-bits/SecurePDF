"""Tests for SecurePDF user registration."""

"""Tests for SecurePDF user registration."""

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import User
from app.security import decode_access_token, hash_password, verify_password
from app.dependencies import get_current_user
from app.security import create_access_token

client = TestClient(app)


@pytest.fixture
def db_session():
    session = SessionLocal()

    test_emails = [
        "newuser@example.com",
        "duplicate@example.com",
        "normalize@example.com",
        "login@example.com",
        "wrongpassword@example.com",
        "inactive@example.com",
        "dependency@example.com",
        "inactive-dependency@example.com",
    ]

    try:
        session.query(User).filter(
            User.email.in_(test_emails)
        ).delete(synchronize_session=False)
        session.commit()

        yield session

    finally:
        session.rollback()

        session.query(User).filter(
            User.email.in_(test_emails)
        ).delete(synchronize_session=False)
        session.commit()

        session.close()


def test_register_user_success(db_session):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Test User",
            "email": "newuser@example.com",
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["name"] == "Test User"
    assert data["email"] == "newuser@example.com"
    assert data["is_active"] is True
    assert "id" in data
    assert "password_hash" not in data

    user = db_session.query(User).filter(
        User.email == "newuser@example.com"
    ).first()

    assert user is not None
    assert user.password_hash != "TestPassword123!"
    assert verify_password(
        "TestPassword123!",
        user.password_hash,
    )


def test_register_user_duplicate_email(db_session):
    first_response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "First User",
            "email": "duplicate@example.com",
            "password": "TestPassword123!",
        },
    )

    assert first_response.status_code == 201

    second_response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Second User",
            "email": "duplicate@example.com",
            "password": "AnotherPassword123!",
        },
    )

    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "A user with this email already exists."
    )


def test_register_user_rejects_short_password():
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Test User",
            "email": "shortpassword@example.com",
            "password": "short",
        },
    )

    assert response.status_code == 422

def test_register_user_normalizes_email(db_session):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Test User",
            "email": "  NORMALIZE@EXAMPLE.COM  ",
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 201

    data = response.json()
    assert data["email"] == "normalize@example.com"

    user = db_session.query(User).filter(
        User.email == "normalize@example.com"
    ).first()

    assert user is not None

def test_login_user_success(db_session):
    password = "LoginPassword123!"

    user = User(
        name="Login Test User",
        email="login@example.com",
        password_hash=hash_password(password),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "login@example.com",
            "password": password,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"

    payload = decode_access_token(data["access_token"])
    assert payload["sub"] == user.id
    assert "exp" in payload


def test_login_user_rejects_wrong_password(db_session):
    password = "CorrectPassword123!"

    user = User(
        name="Wrong Password User",
        email="wrongpassword@example.com",
        password_hash=hash_password(password),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "wrongpassword@example.com",
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_login_user_rejects_unknown_email():
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "doesnotexist@example.com",
            "password": "SomePassword123!",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_login_user_rejects_inactive_user(db_session):
    password = "InactivePassword123!"

    user = User(
        name="Inactive User",
        email="inactive@example.com",
        password_hash=hash_password(password),
        is_active=False,
    )
    db_session.add(user)
    db_session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "inactive@example.com",
            "password": password,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "User account is inactive."

def test_get_current_user_with_valid_token(db_session):
    user = User(
        name="Dependency Test User",
        email="dependency@example.com",
        password_hash=hash_password("DependencyPassword123!"),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    token = create_access_token(user.id)

    current_user = get_current_user(
        token=token,
        db=db_session,
    )

    assert current_user.id == user.id
    assert current_user.email == user.email


def test_get_current_user_rejects_invalid_token(db_session):
    with pytest.raises(Exception) as exc_info:
        get_current_user(
            token="invalid.token.value",
            db=db_session,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Could not validate credentials."


def test_get_current_user_rejects_unknown_user(db_session):
    token = create_access_token("00000000-0000-0000-0000-000000000000")

    with pytest.raises(Exception) as exc_info:
        get_current_user(
            token=token,
            db=db_session,
        )

    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_inactive_user(db_session):
    user = User(
        name="Inactive Dependency User",
        email="inactive-dependency@example.com",
        password_hash=hash_password("DependencyPassword123!"),
        is_active=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    token = create_access_token(user.id)

    with pytest.raises(Exception) as exc_info:
        get_current_user(
            token=token,
            db=db_session,
        )

    assert exc_info.value.status_code == 401