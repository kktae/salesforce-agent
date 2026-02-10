"""Simplified OAuth2 authentication configuration for Salesforce ADK."""

import os

from dotenv import load_dotenv
from fastapi.openapi.models import OAuth2, OAuthFlows, OAuthFlowAuthorizationCode
from google.adk.auth.auth_credential import (
    AuthCredential,
    AuthCredentialTypes,
    OAuth2Auth,
)
from google.adk.auth.auth_tool import AuthConfig

load_dotenv()

# Environment configuration
SALESFORCE_LOGIN_URL = os.getenv("SALESFORCE_LOGIN_URL", "https://login.salesforce.com")
SALESFORCE_INSTANCE_URL = os.getenv("SALESFORCE_INSTANCE_URL")
SALESFORCE_CLIENT_ID = os.getenv("SALESFORCE_CLIENT_ID")
SALESFORCE_CLIENT_SECRET = os.getenv("SALESFORCE_CLIENT_SECRET")
SALESFORCE_AUTH_ID = os.getenv("SALESFORCE_AUTH_ID")
SALESFORCE_API_VERSION = os.getenv("SALESFORCE_API_VERSION", "62.0")
AGENT_TIMEZONE = os.getenv("AGENT_TIMEZONE", "Asia/Seoul")
AGENTSPACE_MODE = os.getenv("AGENTSPACE_MODE", "").lower() in ("true", "1", "yes")

# OAuth2 authentication scheme for Salesforce
SALESFORCE_AUTH_SCHEME = OAuth2(
    flows=OAuthFlows(
        authorizationCode=OAuthFlowAuthorizationCode(
            authorizationUrl=f"{SALESFORCE_LOGIN_URL}/services/oauth2/authorize",
            tokenUrl=f"{SALESFORCE_LOGIN_URL}/services/oauth2/token",
            scopes={
                "api": "Salesforce API access",
                "refresh_token": "Refresh token for offline access",
            },
        )
    )
)

# OAuth2 credentials (client_id and client_secret)
SALESFORCE_AUTH_CREDENTIAL = AuthCredential(
    auth_type=AuthCredentialTypes.OAUTH2,
    oauth2=OAuth2Auth(
        client_id=SALESFORCE_CLIENT_ID,
        client_secret=SALESFORCE_CLIENT_SECRET,
        token_endpoint_auth_method="client_secret_post",
    ),
)

# AuthConfig for ADK OAuth flow
SALESFORCE_AUTH_CONFIG = AuthConfig(
    auth_scheme=SALESFORCE_AUTH_SCHEME,
    raw_auth_credential=SALESFORCE_AUTH_CREDENTIAL,
)

# State keys for tool_context.state
INSTANCE_URL_CACHE_KEY = "salesforce_instance_url"
USER_IDENTITY_CACHE_KEY = "salesforce_user_identity"
