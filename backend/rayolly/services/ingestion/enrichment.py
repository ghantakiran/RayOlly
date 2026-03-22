from __future__ import annotations

import socket
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class BaseEnricher(ABC):
    @abstractmethod
    async def enrich(self, attributes: dict[str, Any], resource_attributes: dict[str, Any]) -> None:
        ...


class GeoIPEnricher(BaseEnricher):
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._reader = None
        self._db_path = db_path

    async def start(self) -> None:
        if self._db_path is None:
            logger.info("geoip_enricher.disabled", reason="no database path configured")
            return
        try:
            import maxminddb

            self._reader = maxminddb.open_database(str(self._db_path))
            logger.info("geoip_enricher.started", db_path=str(self._db_path))
        except Exception:
            logger.warning("geoip_enricher.init_failed", db_path=str(self._db_path), exc_info=True)

    async def stop(self) -> None:
        if self._reader is not None:
            self._reader.close()
            self._reader = None

    async def enrich(self, attributes: dict[str, Any], resource_attributes: dict[str, Any]) -> None:
        if self._reader is None:
            return

        ip = attributes.get("net.peer.ip") or attributes.get("client.address")
        if not ip:
            return

        try:
            result = self._reader.get(ip)
            if result is None:
                return

            geo: dict[str, Any] = {}
            if country := result.get("country"):
                geo["geo.country_iso_code"] = country.get("iso_code", "")
                geo["geo.country_name"] = country.get("names", {}).get("en", "")
            if city := result.get("city"):
                geo["geo.city_name"] = city.get("names", {}).get("en", "")
            if location := result.get("location"):
                geo["geo.location.lat"] = location.get("latitude")
                geo["geo.location.lon"] = location.get("longitude")

            attributes.update(geo)
        except Exception:
            logger.debug("geoip_enricher.lookup_failed", ip=ip, exc_info=True)


class KubernetesEnricher(BaseEnricher):
    """Adds K8s metadata from the Kubernetes downward API or API server.

    Stubbed: in production this would query the K8s API or read from
    environment variables injected via the downward API.
    """

    async def enrich(self, attributes: dict[str, Any], resource_attributes: dict[str, Any]) -> None:
        k8s_keys = ("k8s.pod.name", "k8s.namespace.name", "k8s.node.name")
        if any(k in resource_attributes for k in k8s_keys):
            return

        pod_name = resource_attributes.get("k8s.pod.name")
        if pod_name:
            resource_attributes.setdefault("k8s.pod.uid", "")
            resource_attributes.setdefault("k8s.deployment.name", "")
            resource_attributes.setdefault("k8s.namespace.name", "default")


class HostnameEnricher(BaseEnricher):
    def __init__(self) -> None:
        self._hostname: str | None = None

    async def enrich(self, attributes: dict[str, Any], resource_attributes: dict[str, Any]) -> None:
        if "host.name" in resource_attributes:
            return
        if self._hostname is None:
            try:
                self._hostname = socket.gethostname()
            except Exception:
                self._hostname = "unknown"
        resource_attributes["host.name"] = self._hostname


class ServiceCatalogEnricher(BaseEnricher):
    """Adds team/owner information from an internal service catalog.

    Stubbed: in production this would query a service catalog API or
    local cache to resolve service name -> team/owner mapping.
    """

    def __init__(self, catalog: dict[str, dict[str, str]] | None = None) -> None:
        self._catalog = catalog or {}

    async def enrich(self, attributes: dict[str, Any], resource_attributes: dict[str, Any]) -> None:
        service_name = resource_attributes.get("service.name")
        if not service_name or service_name not in self._catalog:
            return

        info = self._catalog[service_name]
        resource_attributes.setdefault("service.team", info.get("team", ""))
        resource_attributes.setdefault("service.owner", info.get("owner", ""))
        resource_attributes.setdefault("service.tier", info.get("tier", ""))


class Enricher:
    """Orchestrates multiple enrichment plugins."""

    def __init__(self, enrichers: list[BaseEnricher] | None = None) -> None:
        self._enrichers = enrichers or []

    def add(self, enricher: BaseEnricher) -> None:
        self._enrichers.append(enricher)

    async def enrich(self, attributes: dict[str, Any], resource_attributes: dict[str, Any]) -> None:
        for enricher in self._enrichers:
            try:
                await enricher.enrich(attributes, resource_attributes)
            except Exception:
                logger.warning(
                    "enricher.failed",
                    enricher=type(enricher).__name__,
                    exc_info=True,
                )
