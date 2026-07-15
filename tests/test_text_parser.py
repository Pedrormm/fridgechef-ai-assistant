from src.fridgechef.models import IgnoredTextFragment, IngredientMention, ManualIngredientExtraction
from src.fridgechef.text_parser import parse_manual_ingredients, split_user_text


def test_manual_parser_accepts_food_and_ignores_non_food_with_agent_injection():
    def extractor(text, fragments):
        return ManualIngredientExtraction(
            accepted=[
                IngredientMention(name="pimientos", quantity_label="5 unidades", source_text="5 pimientos", confidence=0.99),
                IngredientMention(name="pollo", quantity_label="200 gramos", source_text="200 gramos de pollo", confidence=0.99),
                IngredientMention(name="huevos de codorniz", quantity_label="5 unidades", source_text="5 huevos de codorniz", confidence=0.98),
                IngredientMention(name="anchoas en vinagre", quantity_label="Cantidad no indicada", source_text="Anchoas en vinagre", confidence=0.98),
                IngredientMention(name="tomates cherry", quantity_label="Varias unidades", source_text="Unos tomates cherry", confidence=0.98),
            ],
            ignored=[
                IgnoredTextFragment(text="Esta clase es bastante aburrida", reason="No es un alimento."),
                IgnoredTextFragment(text="El pulpo Paul", reason="Es una referencia a un animal famoso, no un ingrediente disponible."),
                IgnoredTextFragment(text="La oveja Dolly", reason="Es una referencia a un animal famoso, no un ingrediente disponible."),
            ],
            reasoning_summary="Se han separado alimentos reales de comentarios y referencias.",
        )

    text = (
        "5 pimientos, 200 gramos de pollo. Esta clase es bastante aburrida. "
        "5 huevos de codorniz. Anchoas en vinagre. El pulpo Paul, ya que España ya ganó. "
        "La oveja Dolly. Unos tomates cherry."
    )
    result = parse_manual_ingredients(text, extractor=extractor)

    assert result.accepted == ["pimientos", "pollo", "huevos de codorniz", "anchoas en vinagre", "tomates cherry"]
    assert len(result.ignored) == 3
    assert result.accepted_items[1].quantity_label == "200 gramos"
    assert result.used_agent


def test_manual_parser_rejects_non_food_sentence_with_agent_injection():
    def extractor(text, fragments):
        return ManualIngredientExtraction(
            accepted=[],
            ignored=[IgnoredTextFragment(text=fragment, reason="No se refiere a alimentos disponibles.") for fragment in fragments],
            reasoning_summary="No hay ingredientes disponibles.",
        )

    result = parse_manual_ingredients("quiero comprar un ordenador y unos zapatos", extractor=extractor)
    assert not result.accepted
    assert result.ignored


def test_split_user_text_preserves_reviewable_fragments():
    text = "5 pimientos, 200 gramos de pollo. Anchoas en vinagre."
    assert split_user_text(text) == ["5 pimientos", "200 gramos de pollo", "Anchoas en vinagre"]


def test_manual_parser_does_not_classify_food_locally_without_agent(monkeypatch):
    def unavailable_agent(text, fragments):
        raise RuntimeError("Semantic agent unavailable during this deterministic test.")

    monkeypatch.setattr("src.fridgechef.text_parser._agentic_extraction", unavailable_agent)

    result = parse_manual_ingredients("5 pimientos, tomates cherry")
    assert not result.accepted
    assert result.ignored
    assert not result.used_agent


def test_plain_ingredient_list_does_not_trigger_search_grounding():
    from src.fridgechef.text_parser import _needs_search_grounding

    assert not _needs_search_grounding("4 patatas", ["4 patatas"])
    assert not _needs_search_grounding(
        "2 huevos, tomates cherry y queso",
        ["2 huevos", "tomates cherry y queso"],
    )


def test_named_reference_can_trigger_search_grounding():
    from src.fridgechef.text_parser import _needs_search_grounding

    assert _needs_search_grounding("El pulpo Paul", ["El pulpo Paul"])
    assert _needs_search_grounding("La oveja Dolly", ["La oveja Dolly"])


def test_json_generation_uses_fallback_model_after_resource_exhausted(monkeypatch):
    from types import SimpleNamespace

    from src.fridgechef import text_parser
    from src.fridgechef.text_parser import _generate_json_from_prompt

    monkeypatch.setattr(
        text_parser,
        "types",
        SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs),
    )

    class ResourceExhausted(Exception):
        code = 429

    calls = []

    class Models:
        def generate_content(self, *, model, contents, config):
            calls.append(model)
            if model == "gemini-2.5-flash":
                raise ResourceExhausted("429 RESOURCE_EXHAUSTED")
            return SimpleNamespace(
                text='{"accepted": [], "ignored": [], "reasoning_summary": "ok", "agent_notes": []}'
            )

    client = SimpleNamespace(models=Models())
    result = _generate_json_from_prompt(
        client,
        ["gemini-2.5-flash", "gemini-2.5-flash-lite"],
        "prompt",
    )

    assert result["reasoning_summary"] == "ok"
    assert calls == ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
