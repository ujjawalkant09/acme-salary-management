"""Tests for the wake page Lambda (wake/index.py). AWS and the site are fakes: no network."""

import base64
import importlib
import json
import sys
from pathlib import Path

import pytest

WAKE_DIR = Path(__file__).resolve().parent.parent / "wake"
CODE = "a" * 64


class FakeEc2:
    def __init__(self, state):
        self.state = state
        self.started = []

    def describe_instances(self, InstanceIds):
        return {"Reservations": [{"Instances": [{"State": {"Name": self.state}}]}]}

    def start_instances(self, InstanceIds):
        self.started.append(InstanceIds)


class FakeSsm:
    def __init__(self):
        self.reads = []

    def get_parameter(self, Name, WithDecryption):
        self.reads.append((Name, WithDecryption))
        return {"Parameter": {"Value": CODE}}


@pytest.fixture
def wake(monkeypatch, tmp_path):
    # Never read the author's ~/.aws: boto3 gets an empty config and fake keys.
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "aws-config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "aws-credentials"))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-south-1")
    monkeypatch.setenv("INSTANCE_ID", "i-0abc")
    monkeypatch.setenv("CODE_PARAM", "/acme-salary/wake/WAKE_CODE")
    monkeypatch.setenv("SITE_URL", "https://acme.example.com")
    monkeypatch.syspath_prepend(str(WAKE_DIR))
    sys.modules.pop("index", None)
    module = importlib.import_module("index")
    module.ec2 = FakeEc2("stopped")
    module.ssm = FakeSsm()
    module.site_healthy = lambda: True
    return module


def call(wake, route, body=None, base64_body=False):
    event = {"routeKey": route}
    if body is not None:
        event["body"] = base64.b64encode(body.encode()).decode() if base64_body else body
        event["isBase64Encoded"] = base64_body
    response = wake.handler(event, None)
    return response["statusCode"], response


def start(wake, code=CODE, **kwargs):
    return call(wake, "POST /start", json.dumps({"code": code}), **kwargs)


# --- page ---


def test_page_is_html_with_the_site_url_and_a_strict_policy(wake):
    status, response = call(wake, "GET /")
    assert status == 200
    assert response["headers"]["Content-Type"].startswith("text/html")
    assert response["headers"]["Cache-Control"] == "no-store"
    assert "connect-src 'self'" in response["headers"]["Content-Security-Policy"]
    assert 'const SITE_URL = "https://acme.example.com";' in response["body"]
    assert "{{SITE_URL}}" not in response["body"]


def test_unknown_route_is_404(wake):
    status, _ = call(wake, "GET /admin")
    assert status == 404


# --- status ---


@pytest.mark.parametrize(
    ("state", "healthy", "ready"),
    [
        ("stopped", True, False),
        ("pending", True, False),
        ("running", False, False),
        ("running", True, True),
    ],
)
def test_status_is_ready_only_when_running_and_healthy(wake, state, healthy, ready):
    wake.ec2.state = state
    wake.site_healthy = lambda: healthy
    status, response = call(wake, "GET /status")
    assert status == 200
    assert json.loads(response["body"]) == {"state": state, "ready": ready}


def test_status_never_reads_the_code(wake):
    call(wake, "GET /status")
    assert wake.ssm.reads == []


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_health_check_calls_the_site_health_endpoint(wake, monkeypatch):
    module = importlib.reload(wake)
    urls = []

    def answer(url, timeout):
        urls.append((url, timeout))
        return FakeResponse()

    monkeypatch.setattr(module.urllib.request, "urlopen", answer)
    assert module.site_healthy() is True
    assert urls == [("https://acme.example.com/api/v1/health", 4)]


@pytest.mark.parametrize(
    "error", [TimeoutError("timed out"), ConnectionRefusedError(), OSError("no route")]
)
def test_health_check_failure_is_not_ready(wake, monkeypatch, error):
    module = importlib.reload(wake)

    def refuse(url, timeout):
        raise error

    monkeypatch.setattr(module.urllib.request, "urlopen", refuse)
    assert module.site_healthy() is False


# --- start ---


def test_right_code_starts_a_stopped_server(wake):
    status, response = start(wake)
    assert status == 202
    assert wake.ec2.started == [["i-0abc"]]
    assert wake.ssm.reads == [("/acme-salary/wake/WAKE_CODE", True)]
    assert json.loads(response["body"])["state"] == "pending"


def test_surrounding_spaces_in_the_code_are_ignored(wake):
    status, _ = start(wake, code=f"  {CODE}\n")
    assert status == 202


def test_base64_body_is_read(wake):
    status, _ = start(wake, base64_body=True)
    assert status == 202
    assert wake.ec2.started == [["i-0abc"]]


@pytest.mark.parametrize("code", [CODE[:-1], CODE + "a", "A" * 64, "wrong"])
def test_wrong_code_is_401_and_starts_nothing(wake, code):
    status, _ = start(wake, code=code)
    assert status == 401
    assert wake.ec2.started == []


@pytest.mark.parametrize(
    "body", [None, "", "not json", "[]", '{"code": ""}', '{"code": 123}', '{"other": "x"}']
)
def test_missing_or_invalid_body_is_400_without_reading_the_code(wake, body):
    status, _ = call(wake, "POST /start", body)
    assert status == 400
    assert wake.ssm.reads == []
    assert wake.ec2.started == []


@pytest.mark.parametrize("state", ["running", "pending"])
def test_starting_twice_changes_nothing(wake, state):
    wake.ec2.state = state
    status, response = start(wake)
    assert status == 200
    assert wake.ec2.started == []
    assert json.loads(response["body"])["state"] == state


def test_same_request_twice_starts_the_server_once(wake):
    first, _ = start(wake)
    wake.ec2.state = "pending"
    second, _ = start(wake)
    assert (first, second) == (202, 200)
    assert wake.ec2.started == [["i-0abc"]]


@pytest.mark.parametrize("state", ["stopping", "shutting-down"])
def test_a_stopping_server_is_409(wake, state):
    wake.ec2.state = state
    status, _ = start(wake)
    assert status == 409
    assert wake.ec2.started == []
