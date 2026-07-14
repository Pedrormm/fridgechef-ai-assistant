# FridgeChef_AI_PedroRamonMoreno

FridgeChef AI is a web application that analyses fridge contents from manual input, uploaded photos, browser camera photos or an optional internal camera. It identifies visible ingredients, avoids using doubtful or spoiled items, applies dietary restrictions, and generates practical recipes only when there is enough reliable input.

## Key goals

- Detect visible food from fridge images with Gemini Vision.
- Avoid hallucinated recipes when the image does not contain enough usable food.
- Respect allergies, intolerances, diet, dislikes, time limits and servings.
- Keep the user interface simple, friendly and understandable.
- Keep optional persistence controlled by configuration and explicit user consent.
- Provide a clean structure for local development, ADK experimentation, MCP tools, automation and future Cloud Run deployment.

## Main architecture

| Layer | Purpose |
|---|---|
| Streamlit | Local web frontend and user interaction |
| `src/fridgechef` | Core application logic |
| Gemini / Vertex AI | Vision analysis and recipe generation |
| Deterministic guardrails | Local checks that prevent unsafe or invented recipes |
| ADK | Agent development and demonstration layer |
| MCP | Optional local tool server |
| Firestore / Cloud Storage | Optional persistence with user consent |
| Blink integration | Optional internal camera capture |
| UiPath/Python automation | Optional external automation path |

Before asking Gemini to generate recipes, the backend checks whether the detected input contains at least one usable food item. Items such as water bottles, empty bottles, packaging or unidentified liquids are displayed to the user, but they are not used as recipe bases. If there is not enough reliable food, the app explains it clearly and does not create recipes from invented ingredients.
