"""Agent Marketplace — publish, discover, install, and rate custom agents."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class MarketplaceAgent:
    """An agent published in the marketplace catalog."""

    id: str
    name: str
    description: str
    author: str
    version: str
    category: str  # monitoring, security, cost, compliance, custom
    system_prompt: str
    tools: list[str]
    config_schema: dict = field(default_factory=dict)
    icon_url: str = ""
    downloads: int = 0
    rating: float = 0.0
    rating_count: int = 0
    published_at: str = ""
    verified: bool = False
    pricing: str = "free"  # free, paid


@dataclass
class InstalledAgent:
    """An agent installed by a specific tenant."""

    marketplace_id: str
    tenant_id: str
    enabled: bool = True
    config: dict = field(default_factory=dict)
    installed_at: str = ""


class AgentMarketplace:
    """Manages the agent marketplace catalog and installations."""

    def __init__(self) -> None:
        self._catalog: dict[str, MarketplaceAgent] = {}
        self._installed: dict[str, list[InstalledAgent]] = {}  # tenant_id -> list
        self._seed_catalog()

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    def _seed_catalog(self) -> None:
        """Seed with built-in marketplace agents."""
        now = datetime.now(UTC).isoformat()
        agents = [
            MarketplaceAgent(
                id="mp-cost-optimizer",
                name="Cost Optimizer Agent",
                description=(
                    "Analyzes cloud infrastructure costs, identifies waste, and "
                    "recommends optimizations. Integrates with AWS Cost Explorer, "
                    "GCP Billing, and Azure Cost Management."
                ),
                author="RayOlly",
                version="1.0.0",
                category="cost",
                system_prompt="You are a cloud cost optimization agent...",
                tools=["query_metrics", "get_service_map"],
                downloads=1250,
                rating=4.7,
                rating_count=89,
                verified=True,
                published_at=now,
            ),
            MarketplaceAgent(
                id="mp-security-scanner",
                name="Security Scanner Agent",
                description=(
                    "Detects suspicious patterns in logs: brute force attempts, "
                    "privilege escalation, data exfiltration indicators, and "
                    "unusual access patterns."
                ),
                author="RayOlly",
                version="1.0.0",
                category="security",
                system_prompt="You are a security analysis agent...",
                tools=["query_logs", "query_traces", "get_alerts"],
                downloads=890,
                rating=4.5,
                rating_count=52,
                verified=True,
                published_at=now,
            ),
            MarketplaceAgent(
                id="mp-compliance-auditor",
                name="Compliance Auditor Agent",
                description=(
                    "Checks observability data against SOC2, HIPAA, and GDPR "
                    "requirements. Identifies PII exposure, missing audit trails, "
                    "and retention violations."
                ),
                author="RayOlly",
                version="1.0.0",
                category="compliance",
                system_prompt="You are a compliance auditing agent...",
                tools=["query_logs", "run_query"],
                downloads=430,
                rating=4.3,
                rating_count=28,
                verified=True,
                published_at=now,
            ),
            MarketplaceAgent(
                id="mp-deployment-guardian",
                name="Deployment Guardian Agent",
                description=(
                    "Monitors deployments in real-time, detects regressions "
                    "(error rate, latency, crash rate), and recommends rollback "
                    "when quality gates fail."
                ),
                author="RayOlly",
                version="1.0.0",
                category="monitoring",
                system_prompt="You are a deployment monitoring agent...",
                tools=["query_metrics", "query_logs", "get_alerts", "get_service_map"],
                downloads=670,
                rating=4.6,
                rating_count=45,
                verified=True,
                published_at=now,
            ),
            MarketplaceAgent(
                id="mp-chaos-analyzer",
                name="Chaos Engineering Analyzer",
                description=(
                    "Analyzes results from chaos engineering experiments (Chaos "
                    "Monkey, Litmus, Gremlin). Determines blast radius, recovery "
                    "time, and system resilience."
                ),
                author="Community",
                version="0.9.0",
                category="monitoring",
                system_prompt="You are a chaos engineering analysis agent...",
                tools=["query_logs", "query_metrics", "query_traces"],
                downloads=210,
                rating=4.1,
                rating_count=15,
                verified=False,
                published_at=now,
            ),
        ]
        for agent in agents:
            self._catalog[agent.id] = agent

    def list_catalog(
        self, category: str | None = None
    ) -> list[MarketplaceAgent]:
        """Return catalog agents, optionally filtered by category."""
        agents = list(self._catalog.values())
        if category:
            agents = [a for a in agents if a.category == category]
        return sorted(agents, key=lambda a: a.downloads, reverse=True)

    def get_agent(self, agent_id: str) -> MarketplaceAgent | None:
        """Return a single catalog agent by ID."""
        return self._catalog.get(agent_id)

    # ------------------------------------------------------------------
    # Installation
    # ------------------------------------------------------------------

    def install(
        self, tenant_id: str, agent_id: str, config: dict | None = None
    ) -> InstalledAgent | None:
        """Install a marketplace agent for the given tenant."""
        agent = self._catalog.get(agent_id)
        if not agent:
            return None

        # Prevent duplicate installs
        existing = self._installed.get(tenant_id, [])
        if any(i.marketplace_id == agent_id for i in existing):
            logger.warning(
                "marketplace.already_installed",
                agent=agent_id,
                tenant=tenant_id,
            )
            return None

        installed = InstalledAgent(
            marketplace_id=agent_id,
            tenant_id=tenant_id,
            config=config or {},
            installed_at=datetime.now(UTC).isoformat(),
        )
        self._installed.setdefault(tenant_id, []).append(installed)
        agent.downloads += 1
        logger.info(
            "marketplace.agent_installed", agent=agent.name, tenant=tenant_id
        )
        return installed

    def uninstall(self, tenant_id: str, agent_id: str) -> bool:
        """Uninstall a marketplace agent for the given tenant."""
        installed = self._installed.get(tenant_id, [])
        for i, inst in enumerate(installed):
            if inst.marketplace_id == agent_id:
                installed.pop(i)
                logger.info(
                    "marketplace.agent_uninstalled",
                    agent=agent_id,
                    tenant=tenant_id,
                )
                return True
        return False

    def list_installed(self, tenant_id: str) -> list[dict]:
        """Return installed agents with their catalog metadata."""
        installed = self._installed.get(tenant_id, [])
        result = []
        for inst in installed:
            agent = self._catalog.get(inst.marketplace_id)
            if agent:
                result.append({"agent": agent, "installation": inst})
        return result

    # ------------------------------------------------------------------
    # Ratings
    # ------------------------------------------------------------------

    def rate(self, agent_id: str, rating: float) -> bool:
        """Submit a rating for a marketplace agent (1.0 - 5.0)."""
        if not 1.0 <= rating <= 5.0:
            return False
        agent = self._catalog.get(agent_id)
        if not agent:
            return False
        total = agent.rating * agent.rating_count + rating
        agent.rating_count += 1
        agent.rating = round(total / agent.rating_count, 2)
        return True

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------

    def list_categories(self) -> list[dict]:
        """Return all categories with their agent counts."""
        counts: dict[str, int] = {}
        for agent in self._catalog.values():
            counts[agent.category] = counts.get(agent.category, 0) + 1
        return [
            {"category": cat, "count": cnt}
            for cat, cnt in sorted(counts.items())
        ]
