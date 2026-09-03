#!/opt/app-root/bin/python

import argparse
import json
import logging
import os
import ssl
import time
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class VaultCredentialManager:

    def __init__(self):
        # Get configuration from environment variables
        self.vault_url = os.getenv("VAULT_URL")
        self.vault_secret_path = os.getenv("VAULT_CREDENTIAL_PATH")
        self.vault_role = os.getenv("VAULT_ROLE")
        self.db_username = os.getenv("DB_USERNAME", "postgres")
        self.credentials_file = os.getenv(
            "CREDENTIALS_FILE", "/etc/credentials.properties"
        )
        # ZTVP trusted CA bundle (preferred)
        self.ztvp_ca_bundle = os.getenv(
            "ZTVP_CA_BUNDLE",
            "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
        )
        # Service CA (fallback for backward compatibility)
        self.service_ca_file = os.getenv(
            "SERVICE_CA_FILE",
            "/run/secrets/kubernetes.io/serviceaccount/service-ca.crt",
        )
        self.jwt_token_file = os.getenv(
            "JWT_TOKEN_FILE", "/run/secrets/spiffe/jwt.token"
        )

        # Validate required environment variables
        required_vars = {
            "VAULT_URL": self.vault_url,
            "VAULT_CREDENTIAL_PATH": self.vault_secret_path,
            "VAULT_ROLE": self.vault_role,
        }

        missing_vars = [name for name, value in required_vars.items() if not value]
        if missing_vars:
            missing_str = ", ".join(missing_vars)
            raise ValueError(f"Missing required environment variables: {missing_str}")

        logger.info("Initialized VaultCredentialManager with:")
        logger.info("  VAULT_URL: %s", self.vault_url)
        logger.info("  VAULT_CREDENTIAL_PATH: %s", self.vault_secret_path)
        logger.info("  VAULT_ROLE: %s", self.vault_role)
        logger.info("  DB_USERNAME: %s", self.db_username)
        logger.info("  CREDENTIALS_FILE: %s", self.credentials_file)
        logger.info("  ZTVP_CA_BUNDLE: %s", self.ztvp_ca_bundle)
        logger.info("  SERVICE_CA_FILE: %s", self.service_ca_file)
        logger.info("  JWT_TOKEN_FILE: %s", self.jwt_token_file)

        self.vault_token = None
        self.lease_duration = 0
        self.token_creation_time = None

        # Setup SSL context for CA verification
        self.ssl_context = ssl.create_default_context()

        # Try ZTVP CA bundle first (contains both ingress and service CAs)
        if os.path.exists(self.ztvp_ca_bundle):
            self.ssl_context.load_verify_locations(self.ztvp_ca_bundle)
            logger.info("Loaded ZTVP trusted CA bundle from: %s", self.ztvp_ca_bundle)
        # Fallback to service CA only (for backward compatibility)
        elif os.path.exists(self.service_ca_file):
            self.ssl_context.load_verify_locations(self.service_ca_file)
            logger.info("Loaded service CA from: %s", self.service_ca_file)
        else:
            logger.warning(
                "No CA certificates found at %s or %s. "
                "Using default SSL context. SSL verification may fail.",
                self.ztvp_ca_bundle,
                self.service_ca_file,
            )

    def _make_http_request(
        self, url, method="GET", data=None, headers=None, timeout=30
    ):
        """Helper method to make HTTP requests using urllib"""
        try:
            if headers is None:
                headers = {}

            # Prepare request data
            request_data = None
            if data is not None:
                if isinstance(data, dict):
                    request_data = json.dumps(data).encode("utf-8")
                    headers["Content-Type"] = "application/json"
                else:
                    request_data = (
                        data.encode("utf-8") if isinstance(data, str) else data
                    )

            # Create request
            req = Request(url, data=request_data, headers=headers, method=method)

            # Make request with SSL context and timeout
            response = urlopen(req, context=self.ssl_context, timeout=timeout)

            # Read response
            response_data = response.read().decode("utf-8")
            status_code = response.getcode()

            return {
                "status_code": status_code,
                "text": response_data,
                "json": lambda: (json.loads(response_data) if response_data else {}),
            }

        except HTTPError as e:
            # Handle HTTP errors
            error_data = e.read().decode("utf-8") if e.fp else ""
            return {
                "status_code": e.code,
                "text": error_data,
                "json": lambda: (json.loads(error_data) if error_data else {}),
            }
        except URLError:
            logger.error("URL Error occurred")
            raise
        except Exception:
            logger.error("Request error occurred")
            raise

    def get_spiffe_token(self):
        """Retrieve SPIFFE JWT token"""
        try:
            with open(self.jwt_token_file, "r", encoding="utf-8") as source:
                jwt_svid = source.read()
                logger.info("Successfully retrieved SPIFFE JWT token")
                return jwt_svid
        except Exception:
            logger.error("Failed to retrieve SPIFFE token")
            raise

    def authenticate_with_vault(self):
        """Authenticate with Vault using SPIFFE JWT token"""
        try:
            spiffe_token = self.get_spiffe_token()

            # Vault JWT auth endpoint
            auth_url = f"{self.vault_url}/v1/auth/jwt/login"

            # Authentication payload
            auth_payload = {"role": self.vault_role, "jwt": spiffe_token}

            logger.info("Authenticating with Vault")
            response = self._make_http_request(
                auth_url, method="POST", data=auth_payload, timeout=30
            )

            if response["status_code"] != 200:
                logger.error(
                    "Vault authentication failed: %s - %s",
                    response["status_code"],
                    response["text"],
                )
                raise RuntimeError(
                    f"Vault authentication failed: {response['status_code']}"
                )

            auth_data = response["json"]()

            # Extract client token and lease duration
            self.vault_token = auth_data["auth"]["client_token"]
            self.lease_duration = auth_data["auth"]["lease_duration"]
            self.token_creation_time = datetime.now()

            logger.info("Successfully authenticated with Vault")
            logger.info("Token lease duration: %s seconds", self.lease_duration)

            return True

        except Exception:
            logger.error("Vault authentication error occurred")
            raise

    def retrieve_vault_secret(self):
        """Retrieve secret from Vault using the authenticated token"""
        try:
            if not self.vault_token:
                raise RuntimeError("No valid Vault token available")

            secret_url = f"{self.vault_url}/v1/{self.vault_secret_path}"

            headers = {"X-Vault-Token": self.vault_token}

            logger.info("Retrieving secret from Vault")
            response = self._make_http_request(
                secret_url,
                method="GET",
                headers=headers,
                timeout=30,
            )

            if response["status_code"] != 200:
                logger.error(
                    "Failed to retrieve secret: %s - %s",
                    response["status_code"],
                    response["text"],
                )
                raise RuntimeError(
                    f"Failed to retrieve secret: {response['status_code']}"
                )

            secret_data = response["json"]()
            logger.info("Successfully retrieved secret from Vault")

            return secret_data

        except Exception:
            logger.error("Secret retrieval error occurred")
            raise

    def extract_credentials(self, secret_data):
        """Extract credentials from Vault response"""
        try:
            # Navigate the JSON structure: data.data.db-password
            credentials = secret_data.get("data", {}).get("data", {})

            if not credentials:
                raise RuntimeError("No credentials found in secret data")

            logger.info("Extracted %s credential(s)", len(credentials))

            credentials["db-username"] = self.db_username
            return credentials

        except Exception:
            logger.error("Credential extraction error occurred")
            raise

    def write_properties_file(self, credentials):
        """Write credentials to Java properties file format"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.credentials_file), exist_ok=True)

            with open(self.credentials_file, "w", encoding="utf-8") as f:
                username = credentials["db-username"]
                password = credentials["db-password"]
                f.write("# Generated credentials from Vault\n")
                f.write(f"# Generated at: {datetime.now().isoformat()}\n")
                f.write("\n")
                f.write(f"quarkus.datasource.username={username}\n")
                f.write(f"quarkus.datasource.password={password}\n")

            logger.info("Credentials written to %s", self.credentials_file)

        except Exception:
            logger.error("Error writing properties file")
            raise

    def is_token_renewal_needed(self):
        """Check if token needs renewal (at half of lease duration)"""
        if not self.token_creation_time or not self.lease_duration:
            return True

        elapsed_time = (datetime.now() - self.token_creation_time).total_seconds()
        renewal_threshold = self.lease_duration / 2

        return elapsed_time >= renewal_threshold

    def renew_vault_token(self):
        """Renew Vault token"""
        try:
            if not self.vault_token:
                raise RuntimeError("No valid Vault token to renew")

            renew_url = f"{self.vault_url}/v1/auth/token/renew-self"

            headers = {"X-Vault-Token": self.vault_token}

            logger.info("Attempting to renew Vault token")
            response = self._make_http_request(
                renew_url,
                method="POST",
                headers=headers,
                timeout=30,
            )

            if response["status_code"] == 200:
                renew_data = response["json"]()
                self.lease_duration = renew_data["auth"]["lease_duration"]
                self.token_creation_time = datetime.now()
                logger.info(
                    "Token renewed successfully, new lease: %s seconds",
                    self.lease_duration,
                )
                return True
            else:
                logger.warning(
                    "Token renewal failed: %s. Re-authenticating...",
                    response["status_code"],
                )
                return False

        except Exception:
            logger.warning("Token renewal error occurred. Re-authenticating...")
            return False

    def run(self, init=False):
        """Main execution loop"""
        logger.info("Starting Vault credential manager")

        while True:
            try:
                # Check if we need to authenticate or renew token
                if not self.vault_token or self.is_token_renewal_needed():
                    if self.vault_token and not self.renew_vault_token():
                        # Renewal failed, re-authenticate
                        self.vault_token = None
                    if not self.vault_token:
                        self.authenticate_with_vault()

                # Retrieve and process credentials
                secret_data = self.retrieve_vault_secret()
                credentials = self.extract_credentials(secret_data)
                self.write_properties_file(credentials)

                if init:
                    logger.info("Initialization complete")
                    break

                # Calculate sleep time (50% of lease, min 30s, max 1d)
                sleep_time = min(max(self.lease_duration * 0.5, 30), 86400)
                logger.info(
                    "Sleeping for %i seconds before next check",
                    int(sleep_time),
                )
                time.sleep(sleep_time)

            except KeyboardInterrupt:
                logger.info("Received interrupt signal, shutting down...")
                break
            except Exception:
                logger.error("Error in main loop")
                logger.info("Retrying in 60 seconds...")
                time.sleep(60)


def main():
    parser = argparse.ArgumentParser(
        description="SPIFFE-enabled Vault credential manager"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--init", action="store_true", help="Initialize the credential manager"
    )
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        manager = VaultCredentialManager()
        manager.run(args.init)
    except Exception as e:
        logger.error("Failed to start credential manager")
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
