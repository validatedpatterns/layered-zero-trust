#!/usr/bin/env python3
"""Provision federated Quay robot accounts for short-lived registry tokens.

For every robot in ROBOTS_FILE this script makes sure that:
  * the robot account exists in the Quay organization,
  * its federation trusts the issuer and subject of the identity's
    short-lived Vault identity JWT,
  * it holds the requested role on the repository.

The federation issuer, subject and audience are read from the JWT that the
External Secrets Operator keeps in each identity's federationSecret
(iss = Vault identity OIDC issuer, sub = Vault entity of the identity,
aud = Vault OIDC role client_id). ESO then exchanges that JWT for a
one-hour robot token, so no long-lived registry credential is handed to
workloads.
"""

import base64
import http.cookiejar
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

QUAY_HOST = os.getenv("QUAY_HOST")
ADMIN_USER = os.getenv("QUAY_ADMIN_USER")
ADMIN_PASSWORD = os.getenv("QUAY_ADMIN_PASSWORD")
REPOSITORY = os.getenv("QUAY_REPOSITORY", "")
ROBOTS_FILE = os.getenv("ROBOTS_FILE", "/config/robots.json")
SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
# Optional CA bundle (e.g. the ztvp-trusted-ca ConfigMap) added on top of
# the system trust store, so both publicly signed (Let's Encrypt) and
# cluster-CA-signed Quay endpoints verify
CA_CERT = os.getenv("CA_CERT")
KUBE_API = "https://kubernetes.default.svc"
# Total retry budget; keep it below the Job activeDeadlineSeconds (900)
TIMEOUT_SECONDS = int(os.getenv("TIMEOUT_SECONDS", "780"))
RETRY_INTERVAL = int(os.getenv("RETRY_INTERVAL", "15"))
# Exit 0 when dependencies are not ready in time (Argo CD Sync hook); the
# CronJob converges later
SOFT_FAIL = os.getenv("SOFT_FAIL", "false").lower() == "true"
DEADLINE = time.monotonic() + TIMEOUT_SECONDS

BASE_URL = f"https://{QUAY_HOST}"


class RetryableError(Exception):
    """A dependency is not ready yet (Quay, organization, identity JWT)."""


def log(msg):
    print(f"[{time.strftime('%X')}] {msg}", flush=True)


def give_up(msg):
    if SOFT_FAIL:
        log(f"WARNING: {msg}; the quay-robot-provisioner CronJob will retry")
        sys.exit(0)
    sys.exit(f"ERROR: {msg}")


def retry_or_give_up(err, msg):
    """Fail fast on TLS verification errors, otherwise wait within budget."""
    reason = getattr(err, "reason", err)
    if isinstance(reason, ssl.SSLCertVerificationError):
        sys.exit(f"ERROR: TLS verification failed: {reason}")
    if time.monotonic() + RETRY_INTERVAL > DEADLINE:
        give_up(f"{msg} ({err})")
    log(f"{err}. Retrying in {RETRY_INTERVAL}s")
    time.sleep(RETRY_INTERVAL)


def tls_context():
    # System trust store plus the optional CA bundle, never an unverified
    # connection and never system trust replaced by the bundle alone
    context = ssl.create_default_context()
    if CA_CERT and os.path.isfile(CA_CERT):
        context.load_verify_locations(cafile=CA_CERT)
    return context


TLS = tls_context()
OPENER = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=TLS),
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
)
CSRF = {"token": ""}


def request(method, path, payload=None):
    """Send a request to Quay. Returns (status, parsed_body)."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if CSRF["token"]:
        headers["X-CSRF-Token"] = CSRF["token"]
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, headers=headers, method=method
    )
    try:
        with OPENER.open(req, timeout=30) as resp:
            body = resp.read().decode() or "{}"
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as err:
        body = err.read().decode()
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return err.code, parsed


def read_identity_claims(namespace, secret):
    """Return (iss, sub, aud) of the identity JWT stored by ESO."""
    with open(f"{SA_DIR}/token", encoding="utf-8") as fh:
        sa_token = fh.read().strip()
    req = urllib.request.Request(
        f"{KUBE_API}/api/v1/namespaces/{namespace}/secrets/{secret}",
        headers={"Authorization": f"Bearer {sa_token}"},
    )
    try:
        # The Kubernetes API is signed by the service CA, which is always
        # available in the pod regardless of the Quay CA bundle. Connection
        # and certificate errors are retried, they do not fail fast like
        # Quay TLS verification errors
        kube_tls = ssl.create_default_context(cafile=f"{SA_DIR}/ca.crt")
        with urllib.request.urlopen(req, context=kube_tls, timeout=30) as resp:
            data = json.loads(resp.read().decode()).get("data", {})
    except urllib.error.HTTPError as err:
        raise RetryableError(
            f"identity JWT secret {namespace}/{secret} not available (HTTP {err.code})"
        ) from err
    except OSError as err:
        raise RetryableError(
            f"unable to read identity JWT secret {namespace}/{secret} "
            f"from Kubernetes: {err}"
        ) from err
    if "token" not in data:
        raise RetryableError(f"identity JWT secret {namespace}/{secret} has no token")
    jwt = base64.b64decode(data["token"]).decode().strip()
    payload = jwt.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    aud = claims.get("aud", "")
    if isinstance(aud, list):
        aud = aud[0] if aud else ""
    return claims["iss"], claims["sub"], aud


def refresh_csrf():
    status, body = request("GET", "/csrf_token")
    if status != 200:
        raise RetryableError(f"unable to get CSRF token (HTTP {status})")
    CSRF["token"] = body.get("csrf_token", "")


def wait_for_quay():
    while True:
        try:
            status, _ = request("GET", "/health/instance")
            if status == 200:
                log("Quay is online")
                return
            err = RetryableError(f"Quay health returned HTTP {status}")
        except (urllib.error.URLError, OSError) as exc:
            err = exc
        retry_or_give_up(err, "Quay did not become ready")


def signin():
    refresh_csrf()
    status, body = request(
        "POST",
        "/api/v1/signin",
        {"username": ADMIN_USER, "password": ADMIN_PASSWORD},
    )
    if status != 200 or not body.get("success", False):
        raise RetryableError(f"admin sign-in failed (HTTP {status})")
    # The session is regenerated on sign-in; fetch a matching CSRF token
    refresh_csrf()
    log(f"Signed in to Quay as {ADMIN_USER}")


def ensure_organization(org):
    status, _ = request("GET", f"/api/v1/organization/{org}")
    if status != 200:
        raise RetryableError(f"organization '{org}' not found yet (HTTP {status})")


def ensure_repository(org, name):
    status, _ = request("GET", f"/api/v1/repository/{org}/{name}")
    if status == 200:
        return
    status, body = request(
        "POST",
        "/api/v1/repository",
        {
            "namespace": org,
            "repository": name,
            "visibility": "private",
            "description": "",
            "repo_kind": "image",
        },
    )
    if status not in (200, 201):
        raise RetryableError(f"unable to create repository {org}/{name}: {body}")
    log(f"Created repository {org}/{name}")


def ensure_robot(org, short):
    status, _ = request("GET", f"/api/v1/organization/{org}/robots/{short}")
    if status == 200:
        return
    status, body = request(
        "PUT",
        f"/api/v1/organization/{org}/robots/{short}",
        {"description": "Federated robot for short-lived tokens (managed by ZTVP)"},
    )
    if status not in (200, 201):
        raise RetryableError(f"unable to create robot {org}+{short}: {body}")
    log(f"Created robot {org}+{short}")


def ensure_federation(org, short, issuer, subject, audience):
    path = f"/api/v1/organization/{org}/robots/{short}/federation"
    status, current = request("GET", path)
    if status == 200 and isinstance(current, list) and len(current) == 1:
        item = current[0]
        audiences = item.get("audiences") or []
        if (
            item.get("issuer") == issuer
            and item.get("subject") == subject
            and (not audiences or audience in audiences)
        ):
            if audience and not audiences:
                log(
                    f"WARNING: Quay did not store the federation audience of "
                    f"{org}+{short}; '{audience}' is not enforced by Quay"
                )
            return
    entry = {"issuer": issuer, "subject": subject}
    if audience:
        entry["audiences"] = [audience]
    status, body = request("POST", path, [entry])
    if status == 400 and audience:
        # Older Quay releases do not accept the audiences field
        log(f"Federation with audiences rejected ({body}), retrying without")
        status, body = request("POST", path, [{"issuer": issuer, "subject": subject}])
    if status not in (200, 201):
        raise RetryableError(f"unable to set federation for {org}+{short}: {body}")
    log(f"Federated robot {org}+{short} with issuer {issuer}, subject {subject}")


def ensure_permission(org, name, robot, role):
    path = f"/api/v1/repository/{org}/{name}/permissions/user/{robot}"
    status, body = request("GET", path)
    if status == 200 and body.get("role") == role:
        return
    status, body = request("PUT", path, {"role": role})
    if status not in (200, 201):
        raise RetryableError(
            f"unable to grant {role} on {org}/{name} to {robot}: {body}"
        )
    log(f"Granted {role} on {org}/{name} to {robot}")


def provision(robots):
    org, name = REPOSITORY.split("/", 1)
    # Resolve every identity first, so a missing JWT does not leave a robot
    # half configured
    identities = []
    for robot in robots:
        iss, sub, aud = read_identity_claims(
            robot["namespace"], robot["federationSecret"]
        )
        identities.append((robot, iss, sub, aud))
    signin()
    ensure_organization(org)
    ensure_repository(org, name)
    for robot, iss, sub, aud in identities:
        short = robot["robot"]
        ensure_robot(org, short)
        ensure_federation(org, short, iss, sub, aud)
        ensure_permission(org, name, f"{org}+{short}", robot["role"])


def main():
    if not all([QUAY_HOST, ADMIN_USER, ADMIN_PASSWORD]) or "/" not in REPOSITORY:
        sys.exit(
            "ERROR: QUAY_HOST, QUAY_ADMIN_USER, QUAY_ADMIN_PASSWORD and "
            "QUAY_REPOSITORY (<org>/<name>) are required"
        )
    with open(ROBOTS_FILE, encoding="utf-8") as fh:
        robots = json.load(fh)

    wait_for_quay()
    while True:
        try:
            provision(robots)
            log("Quay robots are up to date")
            return
        except (RetryableError, urllib.error.URLError, OSError) as err:
            retry_or_give_up(err, "unable to provision Quay robots")


if __name__ == "__main__":
    main()
