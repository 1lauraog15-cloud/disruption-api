import pytest
from flask.testing import FlaskClient

from disruption_api.auth import generate_key, hash_key, is_valid_key
from tests.conftest import TEST_API_KEY


def test_hash_is_stable_and_not_the_key() -> None:
    assert hash_key("abc") == hash_key("abc") != "abc"


def test_generated_key_validates_against_its_hash() -> None:
    key, hashed = generate_key()
    assert is_valid_key(key, frozenset({hashed}))
    assert not is_valid_key(key + "x", frozenset({hashed}))


@pytest.mark.parametrize("key", [None, ""])
def test_empty_key_is_invalid(key: str | None) -> None:
    assert not is_valid_key(key, frozenset({hash_key("k")}))


def test_no_configured_keys_rejects_everything() -> None:
    assert not is_valid_key("anything", frozenset())


def test_several_keys_can_be_valid() -> None:
    hashes = frozenset({hash_key("one"), hash_key("two")})
    assert is_valid_key("one", hashes) and is_valid_key("two", hashes)


def test_health_is_public(anon_client: FlaskClient) -> None:
    assert anon_client.get("/health").status_code == 200


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/disruptions"),
        ("get", "/flights/1"),
        ("post", "/flights"),
        ("get", "/stats/delays"),
        ("post", "/airports"),
    ],
)
def test_protected_endpoints_reject_missing_key(anon_client: FlaskClient, method: str, path: str) -> None:
    resp = getattr(anon_client, method)(path)
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "unauthorized"
    assert resp.headers["WWW-Authenticate"] == "ApiKey"


def test_wrong_key_is_rejected(anon_client: FlaskClient) -> None:
    assert anon_client.get("/disruptions", headers={"X-API-Key": "nope"}).status_code == 401


def test_valid_key_is_accepted(anon_client: FlaskClient) -> None:
    assert anon_client.get("/disruptions", headers={"X-API-Key": TEST_API_KEY}).status_code == 200
