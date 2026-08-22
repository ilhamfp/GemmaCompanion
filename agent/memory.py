"""Compact textual and visual memory for a bounded companion session."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Observation:
    direction: str
    image_path: str
    summary: str


@dataclass
class SessionMemory:
    observations: list[Observation] = field(default_factory=list)
    tool_calls: int = 0
    questions: int = 0

    def remember(self, direction: str, image_path: str, summary: str) -> Observation:
        observation = Observation(direction, image_path, " ".join(summary.split()))
        self.observations.append(observation)
        return observation

    def inventory(self) -> str:
        if not self.observations:
            return "No observations yet."
        return "\n".join(
            f"- {item.direction}: {item.summary}" for item in self.observations
        )

    def as_dict(self) -> dict:
        return {
            "observations": [asdict(item) for item in self.observations],
            "tool_calls": self.tool_calls,
            "questions": self.questions,
        }
