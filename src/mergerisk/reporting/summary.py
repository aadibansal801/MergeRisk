"""Terminal summary formatter for canonical analysis results."""

from __future__ import annotations

from mergerisk.domain.findings import CanonicalFinding
from mergerisk.domain.results import AnalysisResult, AnalysisStatus


class ReportFormatter:
    """Render advisory findings and explicit analysis coverage status."""

    def format_terminal(self, result: AnalysisResult) -> str:
        """Format status and finding details without claiming correctness."""
        lines = [f"Analysis status: {result.status.value.upper()}"]
        if not result.findings and result.status is AnalysisStatus.SUCCESS:
            lines.append(
                "Verdict: ADVISORY - No supported risk patterns detected. "
                "Notice: Static analysis cannot prove absence of behavioral conflicts."
            )
        elif result.status is not AnalysisStatus.SUCCESS:
            lines.append(
                "Verdict: INCONCLUSIVE / PARTIAL - Analysis incomplete. "
                "Unsupported constructs or errors encountered."
            )
        else:
            lines.append("Verdict: ADVISORY - Supported risk patterns were detected; review the findings below.")

        for finding in result.findings:
            lines.append("")
            lines.append(f"[{finding.severity.value.upper()}] {finding.rule_id}: {finding.title}")
            for entity in finding.entities:
                lines.append(f"  {entity.branch.value}: {entity.symbol} ({entity.role})")
            for location in finding.locations:
                lines.append(
                    f"  Location: {location.path}:{location.start_line}:{location.start_column}-"
                    f"{location.end_line}:{location.end_column}"
                )
            lines.append(f"  Evidence: {finding.summary}")
            lines.append(f"  Suggested action: {finding.suggested_action}")
        if result.notes:
            lines.append("")
            lines.append("Analysis notes:")
            lines.extend(f"  - {note}" for note in result.notes)
        return "\n".join(lines)
