"""Integration registry and base framework for RayOlly enterprise integrations."""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class IntegrationCategory(str, Enum):
    """Categories of integrations available in RayOlly."""

    ITSM = "itsm"
    COMMUNICATION = "communication"
    CLOUD = "cloud"
    CI_CD = "ci_cd"
    AUTHENTICATION = "authentication"
    STORAGE = "storage"
    MONITORING = "monitoring"
    CUSTOM = "custom"


class IntegrationStatus(str, Enum):
    """Status of an integration instance."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    CONFIGURING = "configuring"


@dataclass
class IntegrationDefinition:
    """Describes an available integration type."""

    id: str
    name: str
    category: IntegrationCategory
    description: str
    icon_url: str
    config_schema: dict[str, Any]
    capabilities: list[str]
    docs_url: str = ""


@dataclass
class IntegrationInstance:
    """A configured instance of an integration for a specific tenant."""

    id: str
    definition_id: str
    tenant_id: str
    name: str
    config: dict[str, Any]
    status: IntegrationStatus = IntegrationStatus.CONFIGURING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_synced: datetime | None = None
    error_message: str | None = None


@dataclass
class SyncResult:
    """Result of an integration sync operation."""

    success: bool
    synced_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    items_synced: int = 0
    items_failed: int = 0
    errors: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


class BaseIntegration(ABC):
    """Abstract base class for all RayOlly integrations.

    Subclasses must define ``name``, ``category``, and ``config_schema``, and
    implement ``test_connection``, ``sync``, and ``execute_action``.
    """

    name: str
    category: IntegrationCategory
    config_schema: dict[str, Any]

    @abstractmethod
    async def test_connection(self, config: dict[str, Any]) -> bool:
        """Validate that the provided configuration can reach the remote service."""

    @abstractmethod
    async def sync(self, instance: IntegrationInstance) -> SyncResult:
        """Perform a full or incremental sync for the given instance."""

    @abstractmethod
    async def execute_action(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a named action (e.g. ``create_incident``) with the given params."""

    def get_definition(self) -> IntegrationDefinition:
        """Return the ``IntegrationDefinition`` derived from class attributes."""
        return IntegrationDefinition(
            id=self.name,
            name=self.name,
            category=self.category,
            description=getattr(self, "description", ""),
            icon_url=getattr(self, "icon_url", ""),
            config_schema=self.config_schema,
            capabilities=getattr(self, "capabilities", []),
            docs_url=getattr(self, "docs_url", ""),
        )


class IntegrationRegistry:
    """Central registry that manages integration types and their instances.

    Usage::

        registry = IntegrationRegistry()
        registry.register(ServiceNowIntegration)
        available = registry.list_available()
    """

    def __init__(self) -> None:
        self._integrations: dict[str, BaseIntegration] = {}
        self._instances: dict[str, IntegrationInstance] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, integration_class: type[BaseIntegration]) -> None:
        """Instantiate and register an integration class."""
        instance = integration_class()
        name = instance.name
        if name in self._integrations:
            logger.warning("Integration '%s' is already registered – overwriting", name)
        self._integrations[name] = instance
        logger.info("Registered integration: %s (%s)", name, instance.category.value)

    def get(self, name: str) -> BaseIntegration:
        """Return a registered integration by name, or raise ``KeyError``."""
        try:
            return self._integrations[name]
        except KeyError:
            raise KeyError(f"Integration '{name}' is not registered") from None

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def list_available(self) -> list[IntegrationDefinition]:
        """Return definitions for every registered integration."""
        return [i.get_definition() for i in self._integrations.values()]

    def list_by_category(self, category: IntegrationCategory) -> list[IntegrationDefinition]:
        """Return definitions filtered to a single category."""
        return [
            i.get_definition()
            for i in self._integrations.values()
            if i.category == category
        ]

    # ------------------------------------------------------------------
    # Instance lifecycle
    # ------------------------------------------------------------------

    async def create_instance(
        self,
        tenant_id: str,
        definition_id: str,
        name: str,
        config: dict[str, Any],
    ) -> IntegrationInstance:
        """Create a new integration instance after validating the connection."""
        integration = self.get(definition_id)

        instance = IntegrationInstance(
            id=str(uuid.uuid4()),
            definition_id=definition_id,
            tenant_id=tenant_id,
            name=name,
            config=config,
            status=IntegrationStatus.CONFIGURING,
        )

        # Attempt to validate the connection before persisting.
        try:
            connected = await integration.test_connection(config)
            instance.status = IntegrationStatus.ACTIVE if connected else IntegrationStatus.ERROR
            if not connected:
                instance.error_message = "Connection test returned False"
        except Exception as exc:
            logger.exception("Connection test failed for %s", definition_id)
            instance.status = IntegrationStatus.ERROR
            instance.error_message = str(exc)

        self._instances[instance.id] = instance
        logger.info(
            "Created integration instance %s (%s) for tenant %s – status=%s",
            instance.id,
            definition_id,
            tenant_id,
            instance.status.value,
        )
        return instance

    async def test_instance(self, instance_id: str) -> bool:
        """Re-test an existing integration instance's connection."""
        instance = self._instances.get(instance_id)
        if instance is None:
            raise KeyError(f"Instance '{instance_id}' not found")

        integration = self.get(instance.definition_id)
        try:
            result = await integration.test_connection(instance.config)
            if result:
                instance.status = IntegrationStatus.ACTIVE
                instance.error_message = None
            else:
                instance.status = IntegrationStatus.ERROR
                instance.error_message = "Connection test returned False"
            return result
        except Exception as exc:
            logger.exception("Test failed for instance %s", instance_id)
            instance.status = IntegrationStatus.ERROR
            instance.error_message = str(exc)
            return False

    async def sync_instance(self, instance_id: str) -> SyncResult:
        """Trigger a sync for the given integration instance."""
        instance = self._instances.get(instance_id)
        if instance is None:
            raise KeyError(f"Instance '{instance_id}' not found")

        integration = self.get(instance.definition_id)
        try:
            result = await integration.sync(instance)
            instance.last_synced = result.synced_at
            if result.success:
                instance.status = IntegrationStatus.ACTIVE
                instance.error_message = None
            else:
                instance.status = IntegrationStatus.ERROR
                instance.error_message = "; ".join(result.errors) if result.errors else "Sync failed"
            return result
        except Exception as exc:
            logger.exception("Sync failed for instance %s", instance_id)
            instance.status = IntegrationStatus.ERROR
            instance.error_message = str(exc)
            return SyncResult(success=False, errors=[str(exc)])

    # ------------------------------------------------------------------
    # Instance helpers
    # ------------------------------------------------------------------

    def get_instance(self, instance_id: str) -> IntegrationInstance:
        """Return an instance by ID or raise ``KeyError``."""
        try:
            return self._instances[instance_id]
        except KeyError:
            raise KeyError(f"Instance '{instance_id}' not found") from None

    def list_instances(self, tenant_id: str) -> list[IntegrationInstance]:
        """List all instances belonging to a tenant."""
        return [i for i in self._instances.values() if i.tenant_id == tenant_id]

    def delete_instance(self, instance_id: str) -> None:
        """Remove an instance from the registry."""
        if instance_id not in self._instances:
            raise KeyError(f"Instance '{instance_id}' not found")
        del self._instances[instance_id]
        logger.info("Deleted integration instance %s", instance_id)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

integration_registry = IntegrationRegistry()
