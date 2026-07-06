from dataclasses import dataclass


@dataclass
class ScoringResult:
    score: float
    summary: str
