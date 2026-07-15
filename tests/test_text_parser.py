from types import SimpleNamespace

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


def test_multiple_fragments_trigger_one_google_search_grounding_request():
    from src.fridgechef.text_parser import _needs_search_grounding

    fragments = [
        "5 tomates podridos",
        "1 pepino",
        "4 patatas",
        "el pulpo Paul",
        "una bombilla",
        "alcachofa",
    ]
    assert _needs_search_grounding(
        ", ".join(fragments),
        fragments,
        mode="multiple_or_ambiguous",
        min_fragments=2,
    )


def test_single_plain_ingredient_does_not_trigger_search_grounding():
    from src.fridgechef.text_parser import _needs_search_grounding

    assert not _needs_search_grounding(
        "4 patatas",
        ["4 patatas"],
        mode="multiple_or_ambiguous",
        min_fragments=2,
    )


def test_single_named_reference_triggers_search_grounding():
    from src.fridgechef.text_parser import _needs_search_grounding

    assert _needs_search_grounding(
        "El pulpo Paul",
        ["El pulpo Paul"],
        mode="multiple_or_ambiguous",
        min_fragments=2,
    )


def test_grounded_mixed_list_preserves_food_quantity_and_spoiled_state(monkeypatch):
    from src.fridgechef import text_parser

    text = (
        "Tengo 5 tomates podridos, 1 pepino, 4 patatas, el pulpo Paul, "
        "una bombilla, los ingleses no saben nada, alcachofa, todo pa atrás, "
        "filete de ternera"
    )
    fragments = split_user_text(text)

    payload = {
        "accepted": [
            {
                "name": "tomates",
                "quantity_label": "5 unidades",
                "state": "spoiled",
                "source_text": "Tengo 5 tomates podridos",
                "confidence": 0.99,
                "notes": ["El usuario indica que están podridos."],
            },
            {
                "name": "pepino",
                "quantity_label": "1 unidad",
                "state": "unknown",
                "source_text": "1 pepino",
                "confidence": 0.99,
                "notes": [],
            },
            {
                "name": "patatas",
                "quantity_label": "4 unidades",
                "state": "unknown",
                "source_text": "4 patatas",
                "confidence": 0.99,
                "notes": [],
            },
            {
                "name": "alcachofa",
                "quantity_label": "Cantidad no indicada",
                "state": "unknown",
                "source_text": "alcachofa",
                "confidence": 0.99,
                "notes": [],
            },
            {
                "name": "filete de ternera",
                "quantity_label": "Cantidad no indicada",
                "state": "unknown",
                "source_text": "filete de ternera",
                "confidence": 0.99,
                "notes": [],
            },
        ],
        "ignored": [
            {"text": "el pulpo Paul", "reason": "Es una referencia cultural."},
            {"text": "una bombilla", "reason": "Es un objeto."},
            {"text": "los ingleses no saben nada", "reason": "Es un comentario."},
            {"text": "todo pa atrás", "reason": "No describe un alimento."},
        ],
        "reasoning_summary": "Se han separado alimentos, cantidades y estado.",
        "agent_notes": ["manual_input_agent"],
    }

    class Models:
        calls = 0

        def generate_content(self, *, model, contents, config):
            self.calls += 1
            metadata = SimpleNamespace(web_search_queries=["pulpo Paul alimento"])
            candidate = SimpleNamespace(grounding_metadata=metadata)
            return SimpleNamespace(
                text=__import__("json").dumps(payload, ensure_ascii=False),
                candidates=[candidate],
            )

    models = Models()
    monkeypatch.setattr(
        text_parser,
        "get_client",
        lambda: SimpleNamespace(models=models),
    )
    monkeypatch.setattr(
        text_parser,
        "get_settings",
        lambda: SimpleNamespace(
            manual_grounding_enabled=True,
            manual_grounding_mode="multiple_or_ambiguous",
            manual_grounding_min_fragments=2,
        ),
    )
    monkeypatch.setattr(
        text_parser,
        "types",
        SimpleNamespace(
            GenerateContentConfig=lambda **kwargs: kwargs,
            Tool=lambda **kwargs: kwargs,
            GoogleSearch=lambda **kwargs: kwargs,
        ),
    )

    grounded = text_parser._ground_manual_input(text, fragments, ["gemini-2.5-flash"])

    assert models.calls == 1
    assert grounded.used
    assert grounded.search_queries == ["pulpo Paul alimento"]
    assert grounded.extraction is not None
    assert [item.name for item in grounded.extraction.accepted] == [
        "tomates",
        "pepino",
        "patatas",
        "alcachofa",
        "filete de ternera",
    ]
    tomatoes = grounded.extraction.accepted[0]
    assert tomatoes.quantity_label == "5 unidades"
    assert tomatoes.state == "spoiled"


def test_json_generation_uses_fallback_model_after_resource_exhausted(monkeypatch):
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
