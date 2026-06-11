import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from career_scout_ai.config import AppConfig
from career_scout_ai.llm.ollama_client import OllamaClient
from career_scout_ai.scoring.prompts import build_system_prompt, build_user_prompt
from career_scout_ai.storage.models import AgentScore, JobListing

logger = logging.getLogger(__name__)


@dataclass
class AgentDefinition:
    name: str
    content: str


@dataclass
class ScoringRunResult:
    agent_name: str
    total_to_score: int
    scored: int
    skipped: int


class ScoringEngine:
    """Orchestrates LLM scoring of job offers against agent rubrics."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.client = OllamaClient(
            base_url=config.ollama_base_url,
            model=config.ollama_model,
            timeout=config.ollama_timeout,
        )
        self.profile_content = self._load_profile()
        self.agents = self._discover_agents()

    def _load_profile(self) -> str:
        """Load user profile from config/profile.md."""
        path = self.config.profile_path
        if not path.exists():
            raise FileNotFoundError(f"Profile not found: {path}")
        return path.read_text(encoding="utf-8")

    def _discover_agents(self) -> list[AgentDefinition]:
        """Discover agent definitions from config/agents/*.md."""
        agents_dir = self.config.agents_dir
        if not agents_dir.exists():
            logger.warning("Agents directory not found: %s", agents_dir)
            return []

        agents = []
        for md_file in sorted(agents_dir.glob("*.md")):
            name = md_file.stem  # e.g. "best_recommendations"
            content = md_file.read_text(encoding="utf-8")
            agents.append(AgentDefinition(name=name, content=content))
            logger.info("Discovered agent: %s", name)

        if not agents:
            logger.warning("No agent files found in %s", agents_dir)

        return agents

    def score_new_offers(self, session: Session) -> list[ScoringRunResult]:
        """Score all unscored non-duplicate offers for each agent."""
        if not self.client.is_available():
            logger.error(
                "Ollama not available at %s — skipping scoring",
                self.config.ollama_base_url,
            )
            return []

        results = []
        for agent in self.agents:
            result = self._score_agent(session, agent)
            results.append(result)

        return results

    def _score_agent(
        self, session: Session, agent: AgentDefinition
    ) -> ScoringRunResult:
        """Score unscored offers for a single agent."""
        offers = self._get_unscored_offers(session, agent.name)
        total = len(offers)
        scored = 0
        skipped = 0

        logger.info(
            "[%s] Scoring %d new offers with model %s",
            agent.name,
            total,
            self.config.ollama_model,
        )

        system_prompt = build_system_prompt(agent.content)

        for i, offer in enumerate(offers, 1):
            user_prompt = build_user_prompt(self.profile_content, offer)
            result = self.client.score_offer(system_prompt, user_prompt)

            if result is None:
                skipped += 1
                logger.warning(
                    "[%s] %d/%d SKIPPED: %s @ %s",
                    agent.name,
                    i,
                    total,
                    offer.title,
                    offer.company,
                )
                continue

            agent_score = AgentScore(
                job_listing_id=offer.id,
                agent_name=agent.name,
                score=result.score,
                summary=result.summary,
                scored_at=datetime.now(),
                model_name=self.config.ollama_model,
            )
            session.add(agent_score)
            session.commit()
            scored += 1

            logger.info(
                "[%s] %d/%d scored %.2f: %s @ %s",
                agent.name,
                i,
                total,
                result.score,
                offer.title,
                offer.company,
            )

        logger.info(
            "[%s] Done: %d scored, %d skipped out of %d",
            agent.name,
            scored,
            skipped,
            total,
        )

        return ScoringRunResult(
            agent_name=agent.name,
            total_to_score=total,
            scored=scored,
            skipped=skipped,
        )

    def _get_unscored_offers(
        self, session: Session, agent_name: str
    ) -> list[JobListing]:
        """Get non-duplicate offers that haven't been scored by this agent."""
        scored_ids_subq = (
            select(AgentScore.job_listing_id)
            .where(AgentScore.agent_name == agent_name)
            .scalar_subquery()
        )

        stmt = (
            select(JobListing)
            .where(
                JobListing.is_duplicate.is_(False),
                JobListing.id.notin_(scored_ids_subq),
            )
            .order_by(JobListing.scraped_at.desc())
        )

        return list(session.scalars(stmt).all())
