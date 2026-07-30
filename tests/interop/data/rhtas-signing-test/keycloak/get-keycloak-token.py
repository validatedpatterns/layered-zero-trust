#!/usr/bin/env python3
import sys

import requests
import urllib3

# Disable SSL warnings for testing
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if len(sys.argv) < 6:
    print(
        "Usage: get-keycloak-token.py <keycloak_url> <realm> <client_id> <username> <password>",
        file=sys.stderr,
    )
    sys.exit(1)

keycloak_url = sys.argv[1]
realm = sys.argv[2]
client_id = sys.argv[3]
username = sys.argv[4]
password = sys.argv[5]

# Construct token endpoint
token_url = f"{keycloak_url}/realms/{realm}/protocol/openid-connect/token"

# Request token using password grant
data = {
    "grant_type": "password",
    "client_id": client_id,
    "username": username,
    "password": password,
    "scope": "openid email profile",
}

try:
    response = requests.post(token_url, data=data, verify=False)
    response.raise_for_status()
    token_data = response.json()
    print(token_data["access_token"])
except Exception as e:
    print(f"Error getting token: {e}", file=sys.stderr)
    if "response" in locals():
        print(f"Response: {response.text}", file=sys.stderr)
    sys.exit(1)
