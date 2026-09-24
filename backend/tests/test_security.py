import time
import uuid

import jwt
import pytest

from app.core.errors import AuthError
from app.core.security import (
    create_access_token, decode_access_token, hash_password, hash_refresh_token,
    needs_rehash, new_refresh_token, verify_password,
)

SECRET = "s" * 40


def test_password_roundtrip():
    stored = hash_password("correct horse battery", iterations=1_000)
    assert stored.startswith("pbkdf2_sha256$1000$")
    assert verify_password("correct horse battery", stored)
    assert not verify_password("wrong horse", stored)


def test_same_password_gets_different_salts():
    assert hash_password("same-password", iterations=1_000) != hash_password("same-password", iterations=1_000)


def test_mangled_hash_is_a_no_not_a_crash():
    assert not verify_password("whatever", "garbage")
    assert not verify_password("whatever", "md5$1$x$y")


def test_needs_rehash_when_iterations_go_up():
    stored = hash_password("pw12345678", iterations=1_000)
    assert needs_rehash(stored, 2_000)
    assert not needs_rehash(stored, 1_000)


def test_access_token_roundtrip():
    user_id = uuid.uuid4()
    token = create_access_token(user_id, SECRET, minutes=5, scope="agent")
    payload = decode_access_token(token, SECRET)
    assert payload.user_id == user_id
    assert payload.scope == "agent"


def test_expired_token_is_rejected_with_its_own_code():
    token = create_access_token(uuid.uuid4(), SECRET, minutes=-1)
    with pytest.raises(AuthError) as err:
        decode_access_token(token, SECRET)
    assert err.value.code == "token_expired"


def test_token_signed_with_another_secret_is_rejected():
    token = create_access_token(uuid.uuid4(), "x" * 40, minutes=5)
    with pytest.raises(AuthError) as err:
        decode_access_token(token, SECRET)
    assert err.value.code == "invalid_token"


def test_token_with_wrong_issuer_is_rejected():
    token = jwt.encode({"sub": str(uuid.uuid4()), "exp": int(time.time()) + 60, "iss": "someone-else"}, SECRET, algorithm="HS256")
    with pytest.raises(AuthError):
        decode_access_token(token, SECRET)


def test_refresh_tokens_only_store_a_hash():
    token, stored = new_refresh_token()
    assert token != stored
    assert hash_refresh_token(token) == stored
    assert len(stored) == 64


def test_verify_password_rejects_a_hash_with_a_broken_digest():
    assert verify_password("hunter22", "pbkdf2_sha256$1000$c2FsdA$not*base64!") is False
