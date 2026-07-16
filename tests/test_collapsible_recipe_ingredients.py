from pathlib import Path


APP_PATH = Path("streamlit_app/app.py")


def _recipe_source() -> str:
    """Return only the recipe renderer so assertions stay focused."""
    source = APP_PATH.read_text(encoding="utf-8")
    return source.split("def show_recipes", 1)[1].split("def analyze_current_inputs", 1)[0]


def test_recipe_ingredients_are_collapsed_by_default():
    source = _recipe_source()

    assert 'with st.expander("🥕 Ingredientes", expanded=False):' in source
    assert 'st.markdown("### Ingredientes")' not in source


def test_collapsed_ingredient_panel_keeps_every_recipe_ingredient():
    source = _recipe_source()
    expander_position = source.index('with st.expander("🥕 Ingredientes", expanded=False):')
    ingredient_loop_position = source.index("for ingredient in recipe.ingredients_used:")
    preparation_position = source.index('st.markdown("### Cómo prepararlo paso a paso")')

    assert expander_position < ingredient_loop_position < preparation_position
    assert 'st.markdown(f"- {sentence_case(ingredient)}")' in source


def test_recipe_ingredient_panel_uses_native_responsive_streamlit_layout():
    source = _recipe_source()

    # Native expanders are keyboard-accessible and automatically match the parent width.
    assert "<details" not in source
    assert "components.html" not in source
    assert "unsafe_allow_html=True" not in source.split(
        'with st.expander("🥕 Ingredientes", expanded=False):', 1
    )[1].split('if recipe.shopping_list:', 1)[0]
