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
