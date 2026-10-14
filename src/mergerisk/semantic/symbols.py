"""Project-local Python symbol definitions and deterministic lookup."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolDefinition:
    """A function or method definition indexed from project source."""

    qualified_name: str
    file_path: str
    line: int
    col: int
    parameters: list[str]
    is_method: bool
    parent_class: str | None


class SymbolTable:
    """Stable collection of local definitions, retaining duplicate identities."""

    def __init__(self, definitions: list[SymbolDefinition] | None = None) -> None:
        self._definitions: dict[str, list[SymbolDefinition]] = {}
        for definition in definitions or []:
            self.add(definition)

    @property
    def definitions(self) -> tuple[SymbolDefinition, ...]:
        """Return all definitions in deterministic qualified-name order."""
        return tuple(
            definition
            for name in sorted(self._definitions)
            for definition in sorted(
                self._definitions[name],
                key=lambda item: (item.file_path, item.line, item.col, tuple(item.parameters)),
            )
        )

    def add(self, definition: SymbolDefinition) -> None:
        """Add one definition without discarding overloads or duplicate declarations."""
        if not definition.qualified_name or not definition.file_path:
            raise ValueError("symbol qualified_name and file_path must be non-empty")
        if definition.line < 1 or definition.col < 0:
            raise ValueError("symbol source coordinates are invalid")
        self._definitions.setdefault(definition.qualified_name, []).append(definition)

    def lookup_all_exact(self, qualified_name: str) -> list[SymbolDefinition]:
        """Return every definition with an exact qualified identity."""
        return sorted(
            self._definitions.get(qualified_name, []),
            key=lambda item: (item.file_path, item.line, item.col, tuple(item.parameters)),
        )

    def lookup_exact(self, qualified_name: str) -> SymbolDefinition | None:
        """Return a unique exact definition, or None when absent or duplicated."""
        definitions = self._definitions.get(qualified_name, [])
        return definitions[0] if len(definitions) == 1 else None

    def lookup_by_suffix(self, suffix: str) -> list[SymbolDefinition]:
        """Return definitions equal to or ending in a qualified-name suffix."""
        if not suffix:
            return []
        return [
            definition
            for definition in self.definitions
            if definition.qualified_name == suffix or definition.qualified_name.endswith(f".{suffix}")
        ]
