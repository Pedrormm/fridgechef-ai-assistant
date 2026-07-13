import pytest

from src.fridgechef.models import UserProfile
from src.fridgechef.preferences import PreferenceValidationError, validate_profile_preferences


@pytest.mark.parametrize(
    "field, known_values, custom_value",
    [
        ("diet", ["Vegetariana"], "Baja en sal"),
        ("allergies", ["Huevo"], "Sésamo"),
        ("intolerances", ["Lactosa"], "Histamina"),
        ("dislikes", ["Cebolla"], "Cilantro"),
        ("goals", ["Comida rápida"], "Comida para llevar mañana"),
    ],
)
def test_custom_preference_is_added_to_profile(monkeypatch, field, known_values, custom_value):
    import src.fridgechef.preferences as preferences

    monkeypatch.setattr(preferences, "_agent_accepts_preference", lambda field, value: True)
    profile = UserProfile(**{field: known_values}, custom_preferences={field: custom_value})

    validated = validate_profile_preferences(profile)

    assert custom_value in getattr(validated, field)
    assert all(value in getattr(validated, field) for value in known_values)


@pytest.mark.parametrize("field", ["diet", "allergies", "intolerances", "dislikes", "goals"])
def test_blank_custom_preference_raises_friendly_error(field):
    profile = UserProfile(custom_preferences={field: "   "})

    with pytest.raises(PreferenceValidationError) as exc_info:
        validate_profile_preferences(profile)

    assert "Otra/Otro" in str(exc_info.value)


def test_unsafe_custom_preference_is_rejected():
    profile = UserProfile(custom_preferences={"diet": "<script>alert(1)</script>"})

    with pytest.raises(PreferenceValidationError):
        validate_profile_preferences(profile)
