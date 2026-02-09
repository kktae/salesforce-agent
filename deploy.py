"""Agent Engine deployment management for Salesforce ADK."""

import json
import logging
import os

import vertexai
from dotenv import load_dotenv
from vertexai.agent_engines import AdkApp

load_dotenv(override=True)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# Environment variables that must NOT be passed to Agent Engine deployments.
# These are reserved by the platform (Google Cloud, Cloud Run, Knative).
_FORBIDDEN_ENV_VARS = {
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_QUOTA_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "PORT",
    "K_SERVICE",
    "K_REVISION",
    "K_CONFIGURATION",
}

# Environment variable keys to forward to the deployed agent.
_DEPLOY_ENV_KEYS = [
    "GOOGLE_GENAI_USE_VERTEXAI",
    "VERTEXAI_PROJECT",
    "VERTEXAI_LOCATION",
    "AGENT_MODEL",
    "SALESFORCE_CLIENT_ID",
    "SALESFORCE_CLIENT_SECRET",
    "SALESFORCE_LOGIN_URL",
    "SALESFORCE_INSTANCE_URL",
    "SALESFORCE_AUTH_ID",
    "LOG_LEVEL",
    "SALESFORCE_ADK_LOG_LEVEL",
    "GOOGLE_ADK_LOG_LEVEL",
    # Tracing / Telemetry
    "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY",
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
]


class DeploymentManager:
    """Manages Agent Engine deployments for the Salesforce ADK agent."""

    def __init__(
        self,
        project: str | None = None,
        location: str | None = None,
        staging_bucket: str | None = None,
    ):
        self.project = project or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = location or os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        self.staging_bucket = staging_bucket or os.getenv("STAGING_BUCKET")

        logger = logging.getLogger(__name__)
        logger.info("GOOGLE_CLOUD_PROJECT: %s", self.project)
        logger.info("GOOGLE_CLOUD_LOCATION: %s", self.location)
        logger.info("STAGING_BUCKET: %s", self.staging_bucket)

        vertexai.init(
            project=self.project,
            location=self.location,
            staging_bucket=self.staging_bucket,
        )
        self._client = vertexai.Client(  # type: ignore[reportCallIssue]
            project=self.project,
            location=self.location,
        )

    def _get_deploy_env_vars(self) -> dict[str, str]:
        """Collect environment variables to forward to the deployment.

        Reads the allow-listed keys from the current environment, skipping any
        that are empty or match forbidden patterns.
        """
        env_vars: dict[str, str] = {}
        for key in _DEPLOY_ENV_KEYS:
            if key in _FORBIDDEN_ENV_VARS:
                continue
            value = os.getenv(key)
            if value is not None:
                env_vars[key] = value
        return env_vars

    @staticmethod
    def _get_requirements() -> list[str]:
        """Return pip requirements for the deployed agent."""
        return [
            "cloudpickle",
            "pydantic",
            "google-cloud-aiplatform[agent_engines,adk]",
            "google-adk",
            "simple-salesforce",
            "python-dotenv",
            "litellm",
        ]

    @staticmethod
    def _build_adk_app() -> AdkApp:
        """Wrap the root agent in an AdkApp for deployment."""
        from salesforce_adk.agent import root_agent

        return AdkApp(agent=root_agent)

    @staticmethod
    def _get_labels(labels: dict[str, str] | None = None) -> dict[str, str]:
        """Resolve labels from argument or AGENT_LABELS env var (JSON string)."""
        if labels is not None:
            return labels
        raw = os.getenv("AGENT_LABELS")
        if raw:
            return json.loads(raw)
        return {}

    def create(
        self,
        display_name: str | None = None,
        description: str | None = None,
        gcs_dir_name: str | None = None,
        labels: dict[str, str] | None = None,
        min_instances: int | None = None,
        max_instances: int | None = None,
    ):
        """Create a new Agent Engine deployment.

        Returns the created AgentEngine instance.
        """
        display_name = display_name or os.getenv(
            "AGENT_DISPLAY_NAME", "Salesforce ADK Agent"
        )
        description = description or os.getenv(
            "AGENT_DESCRIPTION",
            "Salesforce specialist agent for querying, managing records, and accessing metadata",
        )
        if gcs_dir_name is None:
            gcs_dir_name = os.getenv("GCS_DIR_NAME")
        resolved_labels = self._get_labels(labels)
        if min_instances is None:
            raw = os.getenv("AGENT_MIN_INSTANCES")
            if raw is not None:
                min_instances = int(raw)
        if max_instances is None:
            raw = os.getenv("AGENT_MAX_INSTANCES")
            if raw is not None:
                max_instances = int(raw)

        app = self._build_adk_app()
        config: dict = {
            "staging_bucket": self.staging_bucket,
            "gcs_dir_name": gcs_dir_name,
            "requirements": self._get_requirements(),
            "extra_packages": ["./salesforce_adk"],
            "display_name": display_name,
            "description": description,
            "labels": resolved_labels,
            "env_vars": self._get_deploy_env_vars(),
        }
        if min_instances is not None:
            config["min_instances"] = min_instances
        if max_instances is not None:
            config["max_instances"] = max_instances

        remote_agent = self._client.agent_engines.create(
            agent=app,
            config=config,
        )
        return remote_agent

    def update(
        self,
        resource_name: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        gcs_dir_name: str | None = None,
        labels: dict[str, str] | None = None,
        min_instances: int | None = None,
        max_instances: int | None = None,
    ):
        """Update an existing Agent Engine deployment.

        Returns the updated AgentEngine instance.
        """
        resource_name = resource_name or os.getenv("AGENT_RESOURCE_NAME")
        if not resource_name:
            raise ValueError(
                "resource_name is required. Pass it directly or set AGENT_RESOURCE_NAME in .env"
            )
        if gcs_dir_name is None:
            gcs_dir_name = os.getenv("GCS_DIR_NAME")
        resolved_labels = self._get_labels(labels)

        app = self._build_adk_app()
        config: dict = {
            "staging_bucket": self.staging_bucket,
            "gcs_dir_name": gcs_dir_name,
            "requirements": self._get_requirements(),
            "extra_packages": ["./salesforce_adk"],
            "labels": resolved_labels,
            "env_vars": self._get_deploy_env_vars(),
        }
        if display_name is not None:
            config["display_name"] = display_name
        if description is not None:
            config["description"] = description
        if min_instances is not None:
            config["min_instances"] = min_instances
        if max_instances is not None:
            config["max_instances"] = max_instances

        remote_agent = self._client.agent_engines.update(
            name=resource_name,
            agent=app,
            config=config,
        )
        return remote_agent

    def delete(
        self,
        resource_name: str | None = None,
        force: bool = True,
    ) -> None:
        """Delete an Agent Engine deployment."""
        resource_name = resource_name or os.getenv("AGENT_RESOURCE_NAME")
        if not resource_name:
            raise ValueError(
                "resource_name is required. Pass it directly or set AGENT_RESOURCE_NAME in .env"
            )

        self._client.agent_engines.delete(name=resource_name, force=force)

    def get(self, resource_name: str | None = None):
        """Get details of an Agent Engine deployment.

        Returns the AgentEngine instance.
        """
        resource_name = resource_name or os.getenv("AGENT_RESOURCE_NAME")
        if not resource_name:
            raise ValueError(
                "resource_name is required. Pass it directly or set AGENT_RESOURCE_NAME in .env"
            )

        return self._client.agent_engines.get(name=resource_name)

    def list(self, filter_str: str = "") -> list:
        """List Agent Engine deployments.

        Args:
            filter_str: Optional filter expression (e.g. 'display_name="My Agent"').

        Returns a list of AgentEngine instances.
        """
        config = {}
        if filter_str:
            config["filter"] = filter_str

        return list(
            self._client.agent_engines.list(config=config)
            if config
            else self._client.agent_engines.list()
        )
