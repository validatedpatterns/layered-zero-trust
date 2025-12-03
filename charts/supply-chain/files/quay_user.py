#!/usr/bin/env python3

import http.cookiejar
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Configuration
QUAY_HOST = os.getenv("QUAY_HOST")
USERNAME = os.getenv("QUAY_ADMIN_USER", "username")
EMAIL = os.getenv("QUAY_ADMIN_EMAIL", "user@example.com")
PASSWORD = os.getenv("QUAY_ADMIN_PASSWORD")
CA_CERT = os.getenv("CA_CERT", "/run/secrets/kubernetes.io/serviceaccount/ca.crt")

if not all([QUAY_HOST, PASSWORD]):
    print("ERROR: Missing QUAY_HOST or QUAY_ADMIN_PASSWORD env vars")
    sys.exit(1)

BASE_URL = f"https://{QUAY_HOST}"


def log(msg):
    """Log a message to the console"""
    print(f"[{time.strftime('%X')}] {msg}", flush=True)


# Setup SSL
ctx = ssl.create_default_context()
if os.path.exists(CA_CERT):
    ctx.load_verify_locations(CA_CERT)
    log(f"Using CA certificate from {CA_CERT}")
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
else:
    log(f"WARNING: CA certificate file not found at {CA_CERT}")
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

# Setup Cookies (Required for CSRF)
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=ctx),
    urllib.request.HTTPCookieProcessor(cj),
)


def wait_for_quay():
    """Loop until Quay health endpoint returns 200"""
    url = f"{BASE_URL}/health/instance"
    while True:
        try:
            log(f"Checking Quay health at {url}...")
            with opener.open(url, timeout=10) as response:
                if response.status == 200:
                    log("Quay is Online.")
                    return
        except Exception as e:
            log(f"Quay unavailable ({e}). Retrying in 5s...")
            time.sleep(5)


def get_csrf_token():
    """Fetch CSRF token and prime the cookie jar"""
    url = f"{BASE_URL}/csrf_token"
    with opener.open(url) as response:
        data = json.loads(response.read().decode())
        token = data.get("csrf_token")
    return token


def create_user():
    """Perform the creation flow"""
    try:
        log("Attempting to create user...")
        csrf_token = get_csrf_token()

        url = f"{BASE_URL}/api/v1/user/"
        payload = json.dumps(
            {
                "username": USERNAME,
                "email": EMAIL,
                "password": PASSWORD,
                "_csrf_token": csrf_token,
            }
        ).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "X-CSRF-Token": csrf_token,
        }

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

        with opener.open(req) as response:
            if response.status in [200, 201, 202]:
                log("SUCCESS: User created successfully.")
                return True
    except urllib.error.HTTPError as e:
        if e.code == 400:
            log(f"User '{USERNAME}' already exists. Exiting.")
            return True
        log(f"FAILED to create user: {e.code} {e.reason}")
    except Exception as e:
        log(f"FAILED to create user: {e}")
    return False


# Main
if __name__ == "__main__":
    log("Starting Quay User Automator")

    wait_for_quay()

    while True:
        if create_user():
            sys.exit(0)

        log("Retrying user creation in 10s...")
        time.sleep(10)
