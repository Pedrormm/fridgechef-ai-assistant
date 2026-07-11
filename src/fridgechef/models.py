from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class DetectedIngredient(BaseModel):
    """Single item detected in an image or provided by the user."""

    name: str
    quantity_estimate: Optional[str] = None
    state: str = "unknown"  # fresh, aging, possible_spoiled, unknown
    confidence: float = 0.0
    evidence: Optional[str] = None

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, value: float) -> float:
        """Keep confidence values predictable even when a model returns out-of-range data."""
        return max(0.0, min(1.0, value))


class BarcodeObservation(BaseModel):
    """Visible label, date, brand or barcode information detected in the image."""

    barcode_text: Optional[str] = None
    expiry_text: Optional[str] = None
    product_name_guess: Optional[str] = None
    confidence: float = 0.0
    notes: List[str] = Field(default_factory=list)


class FridgeAnalysis(BaseModel):
    """Structured result returned by the vision step."""

    visible_ingredients: List[DetectedIngredient] = Field(default_factory=list)
    possible_spoiled_items: List[DetectedIngredient] = Field(default_factory=list)
    uncertain_items: List[str] = Field(default_factory=list)
    barcode_observations: List[BarcodeObservation] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class UserProfile(BaseModel):
    """User preferences collected by the web form."""

    diet: List[str] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)
    intolerances: List[str] = Field(default_factory=list)
    dislikes: List[str] = Field(default_factory=list)
    goals: List[str] = Field(default_factory=list)
    time_limit_min: int = 30
    servings: int = 2
    wants_target_recipe: bool = False
    target_recipe: str = ""
    extra_context: str = ""


class RecipeItem(BaseModel):
    """One generated recipe option."""

    title: str
    description: str
    why_this_recipe: str
    time_min: int
    ingredients_used: List[str]
    missing_required_for_target: List[str] = Field(default_factory=list)
    missing_optional: List[str] = Field(default_factory=list)
    steps: List[str]
    anti_waste_tip: str
    allergen_alerts: List[str] = Field(default_factory=list)
    nutrition_notes: List[str] = Field(default_factory=list)
    shopping_list: List[str] = Field(default_factory=list)
    policy_status: str = "unchecked"


class RecipeResponse(BaseModel):
    """Full recipe response returned to the frontend."""

    recipes: List[RecipeItem] = Field(default_factory=list)
    global_explanation: str
    safety_notes: List[str] = Field(default_factory=list)
    save_recommendation: str = ""
    raw_agent_notes: Dict[str, Any] = Field(default_factory=dict)
    can_generate_recipes: bool = True
    no_recipe_reason: str = ""
    recognized_ingredients: List[str] = Field(default_factory=list)


class PipelineResult(BaseModel):
    """Final pipeline result consumed by the Streamlit UI."""

    fridge_analysis: Optional[FridgeAnalysis] = None
    recipe_response: RecipeResponse
    persisted_session_id: Optional[str] = None
    persisted_image_uri: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
