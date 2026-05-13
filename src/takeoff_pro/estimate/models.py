"""Estimating data models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EstimateItem(BaseModel):
    """A unit-cost item from the estimating library."""

    model_config = ConfigDict(extra="forbid")

    item_id: str
    description: str
    unit: str
    unit_cost: float


class AssemblyComponent(BaseModel):
    """An item quantity per unit of takeoff in an assembly."""

    model_config = ConfigDict(extra="forbid")

    item_id: str
    quantity_per_takeoff_unit: float


class Assembly(BaseModel):
    """A named bundle of estimate items."""

    model_config = ConfigDict(extra="forbid")

    assembly_id: str
    name: str
    takeoff_unit: str
    components: list[AssemblyComponent] = Field(default_factory=list)


class BomLine(BaseModel):
    """A priced bill-of-materials line."""

    model_config = ConfigDict(extra="forbid")

    section_id: str
    section_name: str
    item_id: str
    description: str
    unit: str
    quantity: float
    unit_cost: float
    total_cost: float
    source_type: str
    source_id: str
