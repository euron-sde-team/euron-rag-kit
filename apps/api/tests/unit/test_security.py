import uuid
from datetime import timedelta

import fakeredis
import jwt
import pytest

from ragkit_server.core.errors import UnauthorizedError, UnprocessableError
from ragkit_server.core.ratelimit import RateLimiter
from ragkit_server.core.security import (
    decode_session,
    generate_api_key,
    hash_password,
    issue_session,
    parse_api_key,
    validate_password,
    verify_api_key_secret,
    verify_password,
)

SECRET = "test-only-session-secret-0123456789abcdef"


def test_password_hashing_round_trip_and_unknown_user() -> None:
    hashed = hash_password("correct horse battery")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "correct horse battery")
    assert not verify_password(hashed, "wrong horse battery")
    assert not verify_password(None, "correct horse battery")


@pytest.mark.parametrize("password", ["short", "aaaaaaaaaaaa", "x" * 300])
def test_password_policy_rejects_weak_passwords(password: str) -> None:
    with pytest.raises(UnprocessableError):
        validate_password(password)


def test_password_cannot_be_the_email() -> None:
    with pytest.raises(UnprocessableError):
        validate_password("priya@acme-payments.example", email="Priya@Acme-Payments.example")


def test_session_round_trip() -> None:
    user_id = uuid.uuid4()
    token, claims = issue_session(user_id, 3, secret=SECRET, ttl=timedelta(hours=1))
    decoded = decode_session(token, secret=SECRET)
    assert decoded.user_id == user_id
    assert decoded.session_version == 3
    assert decoded.jti == claims.jti


def test_sessions_reject_tampering_expiry_and_foreign_audiences() -> None:
    token, _ = issue_session(uuid.uuid4(), 1, secret=SECRET, ttl=timedelta(hours=1))
    with pytest.raises(UnauthorizedError):
        decode_session(token, secret=SECRET + "x")
    expired, _ = issue_session(uuid.uuid4(), 1, secret=SECRET, ttl=timedelta(seconds=-5))
    with pytest.raises(UnauthorizedError):
        decode_session(expired, secret=SECRET)
    foreign = jwt.encode(
        {"sub": str(uuid.uuid4()), "aud": "other", "iss": "ragkit"}, SECRET, algorithm="HS256"
    )
    with pytest.raises(UnauthorizedError):
        decode_session(foreign, secret=SECRET)


def test_api_keys_are_parsed_and_verified_with_the_pepper() -> None:
    key = generate_api_key("pepper-one")
    assert key.plaintext.startswith("rgk_")
    parsed = parse_api_key(key.plaintext)
    assert parsed is not None
    assert parsed[0] == key.prefix
    assert verify_api_key_secret(parsed[1], key.secret_hash, "pepper-one")
    assert not verify_api_key_secret(parsed[1], key.secret_hash, "pepper-two")
    assert parse_api_key("rgk_tooshort") is None
    assert parse_api_key(key.plaintext + "x") is None


async def test_fixed_window_rate_limit_allows_then_blocks() -> None:
    limiter = RateLimiter(fakeredis.FakeAsyncRedis())
    results = [await limiter.hit("query:key:1", limit=3) for _ in range(4)]
    assert [r.allowed for r in results] == [True, True, True, False]
    assert results[0].remaining == 2
    assert results[-1].headers()["x-ratelimit-limit"] == "3"
    assert (await limiter.hit("query:key:2", limit=1)).allowed
