"""Wake page for the demo server (AWS Lambda behind API Gateway at wake.<domain>).

GET  /        the page: a code box and a "Start demo" button
GET  /status  {"state": <EC2 state>, "ready": <the app answers /api/v1/health>}
POST /start   {"code": "..."}: starts the server if the code matches the one in SSM

Starting is safe to repeat: a server that is already running or starting is left alone.
The server schedules its own auto-stop at boot, so a server started here still stops itself.
"""

import base64
import hmac
import json
import os
import urllib.request
from pathlib import Path

import boto3

INSTANCE_ID = os.environ["INSTANCE_ID"]
CODE_PARAM = os.environ["CODE_PARAM"]
SITE_URL = os.environ["SITE_URL"]
PAGE = (Path(__file__).parent / "page.html").read_text().replace("{{SITE_URL}}", SITE_URL)
# The page's own inline script and style only; it talks to this API and nothing else.
PAGE_HEADERS = {
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; "
    "style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
}

ec2 = boto3.client("ec2")
ssm = boto3.client("ssm")


def handler(event, context):
    route = event.get("routeKey")
    if route == "GET /":
        return {"statusCode": 200, "headers": PAGE_HEADERS, "body": PAGE}
    if route == "GET /status":
        state = instance_state()
        return reply(200, {"state": state, "ready": state == "running" and site_healthy()})
    if route == "POST /start":
        return start(event)
    return reply(404, {"message": "Not found"})


def start(event):
    code = read_code(event)
    if code is None:
        return reply(400, {"message": 'Send the wake code as JSON: {"code": "..."}'})
    if not code_matches(code):
        print("wake: wrong code")
        return reply(401, {"message": "That wake code is not right."})
    state = instance_state()
    if state == "stopped":
        ec2.start_instances(InstanceIds=[INSTANCE_ID])
        print("wake: starting the server")
        return reply(202, {"state": "pending", "message": "Starting the demo."})
    if state in ("pending", "running"):
        return reply(200, {"state": state, "message": "The demo is already on."})
    return reply(409, {"state": state, "message": "The server is stopping. Try again in a minute."})


def read_code(event):
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8", errors="replace")
    try:
        code = json.loads(body).get("code")
    except (ValueError, AttributeError):
        return None
    return code if isinstance(code, str) and code else None


def code_matches(code):
    expected = ssm.get_parameter(Name=CODE_PARAM, WithDecryption=True)["Parameter"]["Value"]
    return hmac.compare_digest(code.strip().encode(), expected.encode())


def instance_state():
    reservations = ec2.describe_instances(InstanceIds=[INSTANCE_ID])["Reservations"]
    return reservations[0]["Instances"][0]["State"]["Name"]


def site_healthy():
    try:
        with urllib.request.urlopen(f"{SITE_URL}/api/v1/health", timeout=4) as response:
            return response.status == 200
    except OSError:
        return False


def reply(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body),
    }
