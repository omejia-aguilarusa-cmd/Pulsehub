"""CLI entry point for the AI provider health check.

Usage
-----
    uv run ai-health          # installed via pyproject.toml [project.scripts]
    uv run python -m takeoff_pro.ai.health_cli

Exit codes
----------
    0  Provider is configured and reachable (warnings may still be present).
    1  Provider is not configured or not reachable.
"""

from __future__ import annotations

import json
import sys

from takeoff_pro.ai.providers import check_ai_health


def main() -> None:
    """Print a JSON health report and exit with 0 (ok) or 1 (not configured)."""
    result = check_ai_health()
    data = result.as_dict()
    print(json.dumps(data, indent=2))

    if result.warnings:
        print("\nWarnings:", file=sys.stderr)
        for warning in result.warnings:
            print(f"  ! {warning}", file=sys.stderr)

    sys.exit(0 if result.configured else 1)


if __name__ == "__main__":
    main()
