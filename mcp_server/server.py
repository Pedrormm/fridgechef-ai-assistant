from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("fridgechef_mcp_server")


@mcp.tool()
def get_anti_waste_rules() -> dict:
    """Return local anti-waste rules used by the recipe workflow."""
    return {
        "rules": [
            "Prioritize ingredients marked as aging before fresher items.",
            "Never use ingredients marked as possible_spoiled.",
            "Suggest freezing or cooking soon when an item looks close to expiry.",
            "Prefer recipes with the fewest missing external ingredients.",
        ]
    }


@mcp.tool()
def get_storage_advice(ingredient: str) -> dict:
    """Return simple storage advice for common ingredients."""
    ingredient_lower = ingredient.lower()
    if "tomate" in ingredient_lower or "tomato" in ingredient_lower:
        return {"ingredient": ingredient, "advice": "Guárdalo fuera de la nevera si está entero; refrigéralo si está cortado."}
    if "queso" in ingredient_lower or "cheese" in ingredient_lower:
        return {"ingredient": ingredient, "advice": "Guárdalo bien envuelto y revisa olor, textura y moho antes de consumirlo."}
    return {"ingredient": ingredient, "advice": "Revisa fecha, olor, textura y envase antes de consumirlo."}


@mcp.tool()
def get_recipe_memory(ingredient: str) -> dict:
    """Return a tiny local recipe memory used as a lightweight RAG example."""
    recipes_by_ingredient = {
        "huevo": ["tortilla", "huevos revueltos", "arroz salteado"],
        "arroz": ["arroz salteado", "ensalada de arroz", "bowl"],
        "calabacin": ["tortilla de calabacín", "crema", "salteado"],
    }
    return {"ingredient": ingredient, "recipes": recipes_by_ingredient.get(ingredient.lower(), [])}


if __name__ == "__main__":
    mcp.run()
