from src.fridgechef.models import DetectedIngredient, FridgeAnalysis
from src.fridgechef.spanish_guard import ensure_fridge_analysis_spanish, ensure_spanish_payload, strip_markup


def test_strip_markup_removes_html_without_dictionary_translation():
    assert strip_markup("<div>Texto limpio</div>") == "Texto limpio"


def test_spanish_payload_agent_rewrites_nested_values():
    payload = {"message": "Texto inicial", "items": [{"note": "Detalle inicial"}]}

    def agent(data, context):
        return {"message": "Texto revisado", "items": [{"note": "Detalle revisado"}]}

    result = ensure_spanish_payload(payload, "prueba", agent=agent)
    assert result["message"] == "Texto revisado"
    assert result["items"][0]["note"] == "Detalle revisado"


def test_fridge_analysis_spanish_guard_preserves_model_shape():
    analysis = FridgeAnalysis(
        visible_ingredients=[DetectedIngredient(name="Nombre inicial", evidence="Detalle inicial", confidence=0.9)],
        notes=["Nota inicial"],
    )

    def agent(data, context):
        data["visible_ingredients"][0]["name"] = "Nombre revisado"
        data["visible_ingredients"][0]["evidence"] = "Detalle revisado"
        data["notes"] = ["Nota revisada"]
        return data

    result = ensure_fridge_analysis_spanish(analysis, agent=agent)
    assert result.visible_ingredients[0].name == "Nombre revisado"
    assert result.visible_ingredients[0].evidence == "Detalle revisado"
    assert result.notes == ["Nota revisada"]
