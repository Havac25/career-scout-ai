from career_scout_ai.storage.models import JobListing

SYSTEM_PROMPT_PREFIX = """You are a career scoring agent.
You will receive a job offer and must evaluate it according to your
scoring rubric below.

You MUST respond with a JSON object containing:
- "score": a float between 0.0 and 1.0
- "summary": a brief career advisor message (2-4 sentences)
  explaining why this score was given

Your scoring rubric and persona:
"""


def build_system_prompt(agent_content: str) -> str:
    """Build system prompt from agent markdown content."""
    return SYSTEM_PROMPT_PREFIX + agent_content


def build_user_prompt(profile_content: str, offer: JobListing) -> str:
    """Build user prompt combining profile and offer data."""
    offer_section = _format_offer(offer)

    return f"""## Candidate Profile

{profile_content}

---

## Job Offer to Evaluate

{offer_section}

---

Evaluate this offer for the candidate. Return JSON with "score" and "summary"."""


def _format_offer(offer: JobListing) -> str:
    """Format a JobListing into readable text for the prompt."""
    parts = [
        f"**Title:** {offer.title}",
        f"**Company:** {offer.company}",
        f"**Portal:** {offer.portal}",
    ]

    if offer.location_raw:
        parts.append(f"**Location:** {offer.location_raw}")
    if offer.workplace_type:
        parts.append(f"**Workplace type:** {offer.workplace_type}")
    if offer.contract_types:
        parts.append(f"**Contract types:** {offer.contract_types}")
    if offer.salary_raw:
        parts.append(f"**Salary:** {offer.salary_raw}")
    if offer.posted_at:
        parts.append(f"**Posted:** {offer.posted_at.strftime('%Y-%m-%d')}")
    if offer.description_raw:
        parts.append(f"\n**Description:**\n{offer.description_raw}")

    return "\n".join(parts)
