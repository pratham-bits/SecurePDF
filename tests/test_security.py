"""Tests for SecurePDF authentication security helpers."""

from datetime import timedelta

import jwt
import pytest

from app.security import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_does_not_return_plaintext():
    password = "TestPassword123!"

    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$argon2")


def test_verify_password_accepts_correct_password():
    password = "TestPassword123!"
    hashed = hash_password(password)

    assert verify_password(password, hashed)


def test_verify_password_rejects_incorrect_password():
    password = "TestPassword123!"
    hashed = hash_password(password)

    assert not verify_password(
        "WrongPassword123!",
        hashed,
    )


def test_create_access_token_contains_user_id():
    token = create_access_token("user-123")

    payload = decode_access_token(token)

    assert payload["sub"] == "user-123"
    assert "exp" in payload


def test_create_access_token_uses_expected_algorithm():
    token = create_access_token("user-123")

    header = jwt.get_unverified_header(token)

    assert header["alg"] == ALGORITHM


def test_expired_access_token_is_rejected():
    token = create_access_token(
        "user-123",
        expires_delta=timedelta(seconds=-1),
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)