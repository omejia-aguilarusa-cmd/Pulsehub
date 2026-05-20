"""Prompt builder for painting takeoff extraction."""

from __future__ import annotations

from dataclasses import dataclass

from takeoff_pro.data.models import Page

PROMPT_VERSION = "painting-takeoff-v1"


@dataclass(frozen=True)
class TakeoffPromptOptions:
    """Estimator options included in a painting takeoff prompt."""

    ceiling_height_ft: float = 9.0
    include_doors: bool = True
    include_windows: bool = True
    include_trim: bool = True


def build_painting_takeoff_prompt(pages: list[Page], options: TakeoffPromptOptions) -> str:
    """Build a strict JSON prompt for painting takeoff extraction."""
    page_lines = "\n".join(
        f"- pageId={page.id}, name={page.name}, scaleSource={page.scale_source or 'unknown'}"
        for page in pages
    )
    return f"""
You are an expert painting estimator analyzing architectural construction plans.
Extract painting-relevant takeoff quantities only. Do not guess beyond what is visible.
If a quantity is estimated, mark it in assumptions and include confidence.
Return strict JSON only. Do not include markdown.

Scope: painting
Prompt version: {PROMPT_VERSION}
Default ceiling height: {options.ceiling_height_ft:g} ft
Include doors: {str(options.include_doors).lower()}
Include windows: {str(options.include_windows).lower()}
Include trim: {str(options.include_trim).lower()}

Use these formulas when perimeter/floor area and opening counts are available:
wall_sf = perimeter_ft * ceiling_height_ft - door_count * 21 - window_count * 15
ceiling_sf = floor_area_sf
baseboard_lf = perimeter_ft
door_trim_lf = door_count * 17
window_trim_lf = window_count * 12
total_trim_lf = baseboard_lf + door_trim_lf + window_trim_lf

Pages:
{page_lines}

Required JSON schema:
{{
  "rooms": [
    {{
      "id": "string",
      "name": "string",
      "type": "office | bathroom | corridor | lobby | storage | mechanical | unknown",
      "pageId": "string",
      "locationDescription": "string",
      "confidence": 0.0,
      "floorAreaSf": null,
      "perimeterFt": null,
      "wallSf": null,
      "ceilingSf": null,
      "doorCount": 0,
      "windowCount": 0,
      "trimLf": null,
      "assumptions": []
    }}
  ],
  "elements": [
    {{
      "type": "door | window | wall | special_surface | note | unknown",
      "count": 0,
      "pageId": "string",
      "locationDescription": "string",
      "confidence": 0.0
    }}
  ],
  "totals": {{
    "floorAreaSf": 0,
    "wallSf": 0,
    "ceilingSf": 0,
    "doorCount": 0,
    "windowCount": 0,
    "trimLf": 0
  }},
  "warnings": [],
  "confidenceScore": 0.0
}}
""".strip()
