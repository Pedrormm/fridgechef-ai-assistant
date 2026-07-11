# Arquitectura FridgeChef AI

El sistema separa el frontend Streamlit, la lógica de aplicación, los agentes ADK, el servidor MCP, la persistencia y la automatización. Esta separación permite probar cada módulo por separado y desplegar en Cloud Run.

## Flujo principal

1. El usuario escribe ingredientes, sube foto, hace foto desde móvil/PC o llama a cámara Blink.
2. El agente de visión analiza ingredientes, posibles alimentos en mal estado y etiquetas/códigos.
3. El orquestador genera contexto para los subagentes.
4. El agente nutricional aplica restricciones.
5. El agente de recetas genera 3 platos.
6. El guardrail local valida que no haya lácteos si hay intolerancia a lactosa, ni productos animales si es vegano, etc.
7. El usuario decide si guarda o no datos en Firestore/Cloud Storage.
