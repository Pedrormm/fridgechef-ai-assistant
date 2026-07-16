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
    recipe_count: int = 2
    custom_preferences: Dict[str, str] = Field(default_factory=dict)
    wants_target_recipe: bool = False
    target_recipe: str = ""
    extra_context: str = ""


class RecipeItem(BaseModel):
    """One generated recipe option."""

    title: str
    description: str
    why_this_recipe: str
    time_min: int
    prep_time_min: Optional[int] = None
    cook_time_min: Optional[int] = None
    servings: Optional[int] = None
    category: str = ""
    cuisine: str = ""
    calories_per_serving: Optional[int] = None
    ingredients_used: List[str]
    missing_required_for_target: List[str] = Field(default_factory=list)
    missing_optional: List[str] = Field(default_factory=list)
    steps: List[str]
    anti_waste_tip: str
    allergen_alerts: List[str] = Field(default_factory=list)
    nutrition_notes: List[str] = Field(default_factory=list)
    shopping_list: List[str] = Field(default_factory=list)
    policy_status: str = "unchecked"
    image_base64: str = ""
    image_mime_type: str = "image/png"
    image_prompt: str = ""
    image_generation_error: str = ""


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


class InventoryItem(BaseModel):
    """Normalized fridge inventory item shown in the UI and optionally persisted."""

    name: str
    normalized_name: str
    quantity: int = 1
    quantity_label: str = "Cantidad no indicada"
    quantity_parts: Dict[str, float] = Field(default_factory=dict)
    state: str = "unknown"
    expiry_text: Optional[str] = None
    confidence: float = 0.0
    sources: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)

    @field_validator("quantity")
    @classmethod
    def keep_positive_quantity(cls, value: int) -> int:
        """Avoid displaying zero or negative quantities after merges."""
        return max(1, int(value or 1))

    @field_validator("quantity_parts", mode="before")
    @classmethod
    def keep_positive_quantity_parts(cls, value: object) -> Dict[str, float]:
        """Ignore invalid persisted quantity fragments without breaking legacy rows."""
        if not isinstance(value, dict):
            return {}
        result: Dict[str, float] = {}
        for raw_unit, raw_amount in value.items():
            unit = str(raw_unit or "").strip()
            if not unit:
                continue
            try:
                amount = float(raw_amount)
            except (TypeError, ValueError):
                continue
            if amount > 0:
                result[unit] = amount
        return result

    @field_validator("confidence")
    @classmethod
    def keep_confidence_range(cls, value: float) -> float:
        """Keep confidence values display-safe and comparable."""
        return max(0.0, min(1.0, float(value or 0.0)))


class InventoryQuantityChange(BaseModel):
    """Quantity delta produced when an incoming item matches a saved item."""

    name: str
    previous_quantity_label: str
    incoming_quantity_label: str
    resulting_quantity_label: str


class InventoryUpdateResult(BaseModel):
    """Result of applying new observations to the current fridge inventory."""

    inventory: List[InventoryItem] = Field(default_factory=list)
    added: List[str] = Field(default_factory=list)
    updated: List[str] = Field(default_factory=list)
    removed: List[str] = Field(default_factory=list)
    ignored: List[str] = Field(default_factory=list)
    quantity_changes: List[InventoryQuantityChange] = Field(default_factory=list)
    mode: str = "replace"


class IngredientMention(BaseModel):
    """Food ingredient extracted by the text-understanding agent."""

    name: str
    quantity_label: str = "Cantidad no indicada"
    state: str = "unknown"
    source_text: str = ""
    confidence: float = 0.0
    notes: List[str] = Field(default_factory=list)

    @field_validator("state", mode="before")
    @classmethod
    def normalize_state(cls, value: object) -> str:
        """Keep manual freshness information inside the states used by the app."""
        raw = str(value or "unknown").strip().lower()
        if raw in {"fresh", "aging", "possible_spoiled", "spoiled", "unknown"}:
            return raw
        if any(marker in raw for marker in ("podrid", "estrope", "caduc", "spoiled", "rotten")):
            return "spoiled"
        if any(marker in raw for marker in ("posible", "possible", "duda", "sospech", "revis")):
            return "possible_spoiled"
        if any(marker in raw for marker in ("madur", "pasad", "aging", "usar pronto")):
            return "aging"
        if any(marker in raw for marker in ("fresc", "fresh", "buen estado")):
            return "fresh"
        return "unknown"

    @field_validator("confidence")
    @classmethod
    def keep_confidence_range(cls, value: float) -> float:
        """Keep confidence values display-safe and comparable."""
        return max(0.0, min(1.0, float(value or 0.0)))


class IgnoredTextFragment(BaseModel):
    """Text fragment rejected by the text-understanding agent."""

    text: str
    reason: str = "No parece un alimento de la nevera."


class ManualIngredientExtraction(BaseModel):
    """Structured output returned by the manual-input extraction agent."""

    accepted: List[IngredientMention] = Field(default_factory=list)
    ignored: List[IgnoredTextFragment] = Field(default_factory=list)
    reasoning_summary: str = ""
    agent_notes: List[str] = Field(default_factory=list)


class RecipeReadinessAssessment(BaseModel):
    """Structured decision returned by the recipe-readiness agent."""

    can_generate: bool = False
    usable_ingredients: List[str] = Field(default_factory=list)
    recognized_items: List[str] = Field(default_factory=list)
    no_recipe_reason: str = ""
    ignored_items: List[IgnoredTextFragment] = Field(default_factory=list)
    reasoning_summary: str = ""


class FridgeQuestionDecision(BaseModel):
    """Structured decision returned by the fridge-question routing agent."""

    is_fridge_related: bool = False
    answer: str = ""
    friendly_redirect: str = ""


class PipelineResult(BaseModel):
    """Final pipeline result consumed by the Streamlit UI."""

    fridge_analysis: Optional[FridgeAnalysis] = None
    recipe_response: RecipeResponse
    persisted_session_id: Optional[str] = None
    persisted_image_uri: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
