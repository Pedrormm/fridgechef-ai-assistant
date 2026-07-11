# FridgeChef_AI_PedroRamonMoreno

FridgeChef AI is a local-first web application that analyses fridge contents from manual input, uploaded photos, browser camera photos or an optional internal camera. It identifies visible ingredients, avoids using doubtful or spoiled items, applies dietary restrictions, and generates practical recipes only when there is enough reliable input.

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

## Local Windows setup

Open the project folder in VS Code:

```powershell
cd C:\FridgeChef\FridgeChef_AI_PedroRamonMoreno
```

Create local files from the templates:

```powershell
copy .env.example .env
```

Place the real local files in the project root:

```text
credentials.json
.env
blink_auth.json  # only needed for the optional internal camera
```

Run the setup once:

```powershell
windows\00_setup_environment.bat
```

## Run the frontend without BAT or PS1

From the VS Code terminal:

```powershell
cd C:\FridgeChef\FridgeChef_AI_PedroRamonMoreno
$env:GOOGLE_APPLICATION_CREDENTIALS="credentials.json"
$env:GOOGLE_GENAI_USE_VERTEXAI="TRUE"
$env:MCP_ENABLED="false"
.\.venv\Scripts\python.exe -m streamlit run streamlit_app\app.py --server.port 8501 --server.address localhost
```

Then open:

```text
http://localhost:8501
```

You can also use VS Code tasks:

```text
Terminal > Run Task... > FridgeChef: Run Streamlit frontend localhost 8501
```

## Optional MCP flow

Terminal 1:

```powershell
.\.venv\Scripts\python.exe -m mcp_server.server
```

Terminal 2:

```powershell
$env:MCP_ENABLED="true"
$env:MCP_SERVER_URL="http://localhost:8088/mcp"
.\.venv\Scripts\python.exe -m streamlit run streamlit_app\app.py --server.port 8501 --server.address localhost
```

## ADK Web

```powershell
.\.venv\Scripts\adk.exe web fridgechef_adk
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Repository safety

Do not commit these local files:

```text
.env
credentials.json
blink_auth.json
.venv/
photos/
```

The `.gitignore` file is configured to keep those files out of Git.

## Current anti-hallucination behavior

Before asking Gemini to generate recipes, the backend checks whether the detected input contains at least one usable food item. Items such as water bottles, empty bottles, packaging or unidentified liquids are displayed to the user, but they are not used as recipe bases. If there is not enough reliable food, the app explains it clearly and does not create recipes from invented ingredients.
