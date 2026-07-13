from __future__ import annotations

import os

from fridgechef_adk.callbacks import after_tool_audit, before_model_guardrail
from fridgechef_adk.tools import collect_fridge_preferences, explain_architecture, local_food_safety_rule

try:
    from google.adk.agents import Agent
    from google.adk.tools import google_search
    from google.adk.tools.agent_tool import AgentTool
except Exception:
    Agent = None
    google_search = None
    AgentTool = None

MODEL = os.getenv("VERTEX_MODEL", "gemini-2.5-flash")

if Agent:
    # Google Search is intentionally isolated in its own agent. ADK's Google
    # Search tool has a single-tool-per-agent limitation, so the root agent uses
    # this component through AgentTool instead of mixing search with local tools.
    search_agent = Agent(
        name="fridgechef_search_agent",
        model=MODEL,
        instruction="""
You are the web-search component of FridgeChef AI Assistant.
Use Google Search only when external evidence is needed, for example:
- ambiguous named references in manual ingredient text,
- general storage or food-safety guidance,
- substitutions and anti-waste advice.
Keep answers short, practical and transparent.
""",
        tools=[google_search],
    )
    search_tool = AgentTool(search_agent) if AgentTool else None

    text_understanding_agent = Agent(
        name="fridgechef_text_understanding_agent",
        model=MODEL,
        instruction="""
You understand natural-language fridge input.
Extract only actual food ingredients that the user says are available.
Reject unrelated sentences, jokes, famous animals, class comments and non-food objects.
Use the search sub-agent only for ambiguous named references.
Return clean ingredient names, quantities and friendly rejection reasons.
""",
        tools=[tool for tool in [search_tool] if tool is not None],
    )
    text_understanding_tool = AgentTool(text_understanding_agent) if AgentTool else None

    readiness_agent = Agent(
        name="fridgechef_recipe_readiness_agent",
        model=MODEL,
        instruction="""
You decide whether the available fridge observations are usable for recipes.
Do not invent ingredients. Do not approve recipes from water only, unidentified liquids,
empty containers, packaging or risky/spoiled food. Explain the decision kindly.
""",
        tools=[],
    )
    readiness_tool = AgentTool(readiness_agent) if AgentTool else None

    tools = [collect_fridge_preferences, explain_architecture, local_food_safety_rule]
    for optional_tool in [search_tool, text_understanding_tool, readiness_tool]:
        if optional_tool:
            tools.append(optional_tool)

    # MCP remains optional so local development works even when the tool server is not running.
    if os.getenv("MCP_ENABLED", "false").lower() == "true":
        try:
            from google.adk.tools.mcp_tool import McpToolset
            from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

            tools.append(
                McpToolset(
                    connection_params=StreamableHTTPConnectionParams(
                        url=os.getenv("MCP_SERVER_URL", "http://localhost:8088/mcp"),
                        headers={"Authorization": f"Bearer {os.getenv('MCP_AUTH_TOKEN', '')}"},
                    ),
                    tool_filter=["get_anti_waste_rules", "get_recipe_memory", "get_storage_advice"],
                )
            )
        except Exception as exc:
            print(f"MCP was not initialized: {exc}")

    root_agent = Agent(
        name="fridgechef_root_agent",
        model=MODEL,
        instruction="""
You are FridgeChef AI Assistant, a practical cooking and fridge-inventory assistant.
Coordinate specialized agents for text understanding, recipe readiness, search, food safety,
preferences, recipes and anti-waste advice.
Respect allergies, intolerances, diets, preferences and food safety.
Do not invent available ingredients. If there is not enough reliable input, say so clearly and kindly.
""",
        tools=tools,
        before_model_callback=before_model_guardrail,
        after_tool_callback=after_tool_audit,
    )
else:
    root_agent = None
