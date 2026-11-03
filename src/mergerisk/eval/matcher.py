"""Typed ground-truth identity and deterministic finding matching."""

from __future__ import annotations

from dataclasses import dataclass

from mergerisk.domain.findings import CanonicalFinding, FindingRelationship, SourceLocation


@dataclass(frozen=True)
class ExpectedEntity:
    """One affected entity and its semantic role in an expected finding."""

    symbol: str
    role: str

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not isinstance(self.role, str):
            raise TypeError("expected entity symbol and role must be strings")
        if not self.symbol.strip():
            raise ValueError("expected entity symbol must be non-empty")
        if not self.role.strip():
            raise ValueError("expected entity role must be non-empty")


@dataclass(frozen=True)
class ExpectedRelationship:
    """Directed relationship asserted by an expected finding."""

    kind: str
    source: str
    target: str
    condition: str

    def __post_init__(self) -> None:
        for name in ("kind", "source", "target", "condition"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise TypeError(f"expected relationship {name} must be a string")
            if not value.strip():
                raise ValueError(f"expected relationship {name} must be non-empty")

    def to_finding_relationship(self) -> FindingRelationship:
        return FindingRelationship(self.kind, self.source, self.target, self.condition)


@dataclass(frozen=True)
class ExpectedFinding:
    """Complete expected-finding identity; roles and relationship are mandatory.

    `location` is an optional path/line anchor. Entity and relationship identity
    remain required, so location drift cannot turn an otherwise wrong finding into
    a match or prevent a correct location-independent match.
    """

    rule_id: str
    entities: tuple[ExpectedEntity, ...]
    relationship: ExpectedRelationship
    location: SourceLocation | None = None
    supported: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.rule_id, str):
            raise TypeError("expected finding rule_id must be a string")
        if not self.rule_id.strip():
            raise ValueError("expected finding rule_id must be non-empty")
        if not isinstance(self.entities, tuple):
            raise TypeError("expected finding entities must be an immutable tuple")
        if not self.entities:
            raise ValueError("expected finding requires at least one affected entity")
        if not isinstance(self.relationship, ExpectedRelationship):
            raise ValueError("expected finding requires an ExpectedRelationship")
        if any(not isinstance(entity, ExpectedEntity) for entity in self.entities):
            raise ValueError("entities must contain ExpectedEntity values with roles")
        symbols = [entity.symbol for entity in self.entities]
        if len(set(symbols)) != len(symbols):
            raise ValueError("expected finding cannot contain duplicate symbols")
        if self.location is not None and not isinstance(self.location, SourceLocation):
            raise TypeError("expected finding location must be a SourceLocation or None")

    @property
    def target_symbols(self) -> set[str]:
        """Compatibility view of the affected symbols."""
        return {entity.symbol for entity in self.entities}

    @property
    def entity_roles(self) -> dict[str, str]:
        """Compatibility view of required entity roles."""
        return {entity.symbol: entity.role for entity in self.entities}

    @property
    def condition(self) -> str:
        """Compatibility view of the required evidence value."""
        return self.relationship.condition

    @property
    def file_path(self) -> str | None:
        """Compatibility view of the optional location path."""
        return self.location.path if self.location else None


class FindingMatcher:
    """Match exact rule/entity-role identity and required relation evidence."""

    def matches(self, expected: ExpectedFinding, actual: CanonicalFinding) -> bool:
        if expected.rule_id != actual.rule_id:
            return False
        actual_roles = {entity.symbol: entity.role for entity in actual.entities}
        if actual_roles != expected.entity_roles:
            return False
        if expected.relationship.to_finding_relationship() not in actual.relationships:
            return False
        if expected.location is not None:
            return any(
                location.path == expected.location.path
                for location in actual.locations
            )
        return True
