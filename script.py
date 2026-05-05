import json
import os
import re
from langchain_ollama import ChatOllama

# ==========================================================
# 1. MOTOR Y CONFIGURACIÓN (Ollama Local)
# ==========================================================
llm = ChatOllama(model="llama3", temperature=0.2)

# Preguntas de competencia: Lo que la ontología DEBE poder responder
COMPETENCY_QUESTIONS = [
    "¿Qué herramienta usa el agente para ejecutar código?",
    "¿Dónde se almacena el historial de conversación?",
    "¿Cómo recupera el LLM información de la memoria externa?"
]

DOMAIN_INFO = f"""
Dominio: Ecosistema de Agentes de IA.
Objetivo: Modelar la interacción entre LLMs, Memorias y Tools.
Preguntas a resolver: {', '.join(COMPETENCY_QUESTIONS)}
"""


# ==========================================================
# 2. UTILIDADES (Limpieza de JSON)
# ==========================================================
def extract_json(text):
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except:
        return None


# ==========================================================
# 3. GENERADOR CON REFINAMIENTO
# ==========================================================
def generate_ontology(version, previous=None, feedback=None):
    prompt = f"""
    Actúa como un Ingeniero Ontológico Senior.
    Genera una ontología técnica en JSON que resuelva estas preguntas de competencia: {COMPETENCY_QUESTIONS}

    Estructura:
    {{
      "clases": {{ "Clase": "Definición" }},
      "relaciones_objeto": [ {{ "sujeto": "", "predicado": "", "objeto": "" }} ],
      "restricciones": [ "Reglas lógicas de la ontología" ]
    }}

    {f"Mejorar esta base: {json.dumps(previous)}" if previous else ""}
    {f"Feedback específico: {feedback}" if feedback else ""}

    RESPONDE SOLO CON JSON.
    """
    print(f"🚀 Generando Versión {version}...")
    response = llm.invoke(prompt)
    return extract_json(response.content)


# ==========================================================
# 4. EVALUADOR TÉCNICO
# ==========================================================
def evaluate(ont):
    if not ont: return 0, "Error"
    score = 0

    # Evaluar si existen las clases clave
    c = str(ont.get("clases", {})).lower()
    if "llm" in c and "memoria" in c and "tool" in c: score += 1

    # Evaluar si hay relaciones (conectividad)
    if len(ont.get("relaciones_objeto", [])) >= 4: score += 1

    # Evaluar si hay restricciones lógicas
    if len(ont.get("restricciones", [])) >= 2: score += 1

    quality = "ALTA" if score == 3 else "MEDIA" if score == 2 else "BAJA"
    return score, quality


# ==========================================================
# 5. EJECUCIÓN
# ==========================================================
def run():
    os.makedirs("practica_final", exist_ok=True)
    actual_ont = None
    actual_feedback = None

    for i in range(1, 10):
        print(f"\n--- ITERACIÓN {i} ---")
        nueva_ont = generate_ontology(i, actual_ont, actual_feedback)

        if not nueva_ont:
            print("⚠️ El modelo falló al generar JSON. Reintentando...")
            continue

        puntos, cal = evaluate(nueva_ont)
        print(f"📊 Evaluación: {cal} ({puntos}/3)")

        # Guardar versión
        with open(f"practica_final/v{i}_ontologia.json", "w", encoding="utf-8") as f:
            json.dump(nueva_ont, f, indent=2, ensure_ascii=False)

        actual_ont = nueva_ont
        # Feedback inteligente para la siguiente vuelta
        if puntos < 3:
            actual_feedback = "Añade más restricciones lógicas y define mejor la jerarquía de Tools."
        else:
            actual_feedback = "Perfecto. Añade ahora propiedades de datos como 'latencia_ms' o 'capacidad_tokens'."

    print("\n✅ Proceso completado. Archivos listos en la carpeta 'practica_final'.")


if __name__ == "__main__":
    run()