import pytest
from rest_framework import exceptions
from rest_framework.test import APIRequestFactory

from lib.authentication import API_KEY_HEADER, InternalApiKeyAuthentication


@pytest.fixture
def auth():
    return InternalApiKeyAuthentication()


@pytest.fixture
def factory():
    return APIRequestFactory()


def _header_kwarg(value):
    return {f"HTTP_{API_KEY_HEADER.upper().replace('-', '_')}": value}


def test_no_header_returns_none(auth, factory, settings):
    settings.INTERNAL_API_KEY = "secret-key"
    request = factory.post("/api/v1/quotes/calculate/")
    assert auth.authenticate(request) is None


def test_correct_key_authenticates(auth, factory, settings):
    settings.INTERNAL_API_KEY = "secret-key"
    request = factory.post("/api/v1/quotes/calculate/", **_header_kwarg("secret-key"))
    user, creds = auth.authenticate(request)
    assert str(user) == "internal-service(n8n)"
    assert user.is_authenticated is True
    assert creds is None


def test_wrong_key_raises(auth, factory, settings):
    settings.INTERNAL_API_KEY = "secret-key"
    request = factory.post("/api/v1/quotes/calculate/", **_header_kwarg("wrong-key"))
    with pytest.raises(exceptions.AuthenticationFailed):
        auth.authenticate(request)


def test_unconfigured_server_key_rejects_everything(auth, factory, settings):
    settings.INTERNAL_API_KEY = ""
    request = factory.post("/api/v1/quotes/calculate/", **_header_kwarg("anything"))
    with pytest.raises(exceptions.AuthenticationFailed):
        auth.authenticate(request)


def test_authenticate_header_present_for_401_semantics(auth, factory):
    request = factory.post("/api/v1/quotes/calculate/")
    assert auth.authenticate_header(request) == API_KEY_HEADER
