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
    # Google Search is isolated in a sub-agent to keep the root agent focused on orchestration.
    search_agent = Agent(
        name="fridgechef_search_agent",
        model=MODEL,
        instruction="""
You are the web-search component of FridgeChef AI.
Use Google Search only for external information such as storage advice, substitutions and general food guidance.
When grounding metadata is available, keep the answer transparent about the source of the information.
""",
        tools=[google_search],
    )
    search_tool = AgentTool(search_agent) if AgentTool else None

    tools = [collect_fridge_preferences, explain_architecture, local_food_safety_rule]
    if search_tool:
        tools.append(search_tool)

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
You are FridgeChef AI, a practical cooking assistant.
Respect allergies, intolerances, diets, preferences, food safety and anti-waste priorities.
Do not invent available ingredients. If there is not enough reliable input, say so clearly and kindly.
Use the search sub-agent only when external information is required.
""",
        tools=tools,
        before_model_callback=before_model_guardrail,
        after_tool_callback=after_tool_audit,
    )
else:
    root_agent = None
