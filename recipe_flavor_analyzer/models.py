from dataclasses import dataclass, field, asdict


@dataclass
class Ingredient:
    name: str
    quantity: str | None = None


@dataclass
class FlavorProfile:
    salt: float = 0.0
    fat: float = 0.0
    acid: float = 0.0
    sweet: float = 0.0
    umami: float = 0.0
    heat: float = 0.0

    def to_scores(self) -> dict[str, int]:
        """Convert to integer scores capped at 0-10."""
        return {
            "salt": max(0, min(10, round(self.salt))),
            "fat": max(0, min(10, round(self.fat))),
            "acid": max(0, min(10, round(self.acid))),
            "sweet": max(0, min(10, round(self.sweet))),
            "umami": max(0, min(10, round(self.umami))),
            "heat": max(0, min(10, round(self.heat))),
        }


@dataclass
class Substitution:
    need: str
    options: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AnalysisResult:
    flavor_scores: dict[str, int]
    diagnosis: str
    decision: str  # KEEP | TWEAK | RESCUE
    fixes: list[str]
    pantry_suggestions: list[str]
    substitutions: list[Substitution]

    def to_dict(self) -> dict:
        return {
            "flavor_scores": self.flavor_scores,
            "diagnosis": self.diagnosis,
            "decision": self.decision,
            "fixes": self.fixes,
            "pantry_suggestions": self.pantry_suggestions,
            "substitutions": [s.to_dict() for s in self.substitutions],
        }
