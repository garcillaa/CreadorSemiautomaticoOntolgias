import json
import os
from langchain_ollama import ChatOllama

# ==========================================================
# 1. MOTOR
# ==========================================================
llm = ChatOllama(model="llama3", temperature=0.2)


# ==========================================================
# 2. INPUT DINÁMICO DEL USUARIO
# ==========================================================
def get_user_input():
    print("\nCONFIGURACIÓN DEL PROBLEMA")

    domain = input("Dominio: ")
    objective = input("Objetivo de la ontología: ")

    print("\nIntroduce preguntas de competencia (escribe 'fin' para terminar):")
    questions = []

    while True:
        q = input(f"Pregunta {len(questions)+1}: ")
        if q.lower() == "fin":
            break
        if q.strip():
            questions.append(q)

    while True:
        try:
            iterations = int(input("\n¿Cuántas iteraciones quieres ejecutar?: "))
            if iterations > 0:
                break
            else:
                print("Introduce un número mayor que 0.")
        except:
            print("Introduce un número válido.")

    return domain, objective, questions, iterations


# ==========================================================
# 3. UTILIDAD JSON
# ==========================================================
def extract_json(text):
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except:
        return None


# ==========================================================
# 4. GENERADOR
# ==========================================================
def generate_ontology(version, domain, objective, questions, previous=None, feedback=None):
    prompt = f"""
    Actúa como un Ingeniero Ontológico Senior.

    Dominio: {domain}
    Objetivo: {objective}

    La ontología DEBE poder responder estas preguntas:
    {questions}

    Estructura:
    {{
      "clases": {{ "Clase": "Definición" }},
      "relaciones_objeto": [ {{ "sujeto": "", "predicado": "", "objeto": "" }} ],
      "restricciones": [ "Reglas lógicas de la ontología" ]
    }}

    {f"Mejorar esta base: {json.dumps(previous, ensure_ascii=False)}" if previous else ""}
    {f"Feedback específico: {feedback}" if feedback else ""}

    RESPONDE SOLO CON JSON.
    """

    print(f"\nGenerando Versión {version}...")
    response = llm.invoke(prompt)
    return extract_json(response.content)


# ==========================================================
# 5. EVALUADOR
# ==========================================================
def evaluate(ont):
    if not ont:
        return 0, "ERROR"

    score = 0
    c = str(ont.get("clases", {})).lower()

    if any(k in c for k in ["llm", "agente", "memoria", "tool"]):
        score += 1

    if len(ont.get("relaciones_objeto", [])) >= 4:
        score += 1

    if len(ont.get("restricciones", [])) >= 2:
        score += 1

    quality = "ALTA" if score == 3 else "MEDIA" if score == 2 else "BAJA"
    return score, quality


# ==========================================================
# 6. REVISIÓN HUMANA
# ==========================================================
def human_review(ontology):
    print("\n===== REVISIÓN HUMANA =====")
    print(json.dumps(ontology, indent=2, ensure_ascii=False))

    decision = input("\n¿Aceptar ontología? (s = sí / n = no / e = editar): ").strip().lower()

    if decision == "s":
        return ontology, None

    elif decision == "n":
        feedback = input("Introduce feedback para mejorar: ")
        return None, feedback

    elif decision == "e":
        print("Pega la versión corregida en JSON:")
        edited = input()

        try:
            return json.loads(edited), None
        except:
            print("JSON inválido. Se mantiene la versión original.")
            return ontology, None

    return ontology, None


# ==========================================================
# 7. EJECUCIÓN
# ==========================================================
def run():
    os.makedirs("practica_final", exist_ok=True)

    domain, objective, questions, iterations = get_user_input()

    actual_ont = None
    actual_feedback = None

    for i in range(1, iterations + 1):
        print(f"\n--- ITERACIÓN {i} ---")

        nueva_ont = generate_ontology(
            i, domain, objective, questions,
            actual_ont, actual_feedback
        )

        if not nueva_ont:
            print("Error generando JSON. Reintentando...")
            continue

        puntos, cal = evaluate(nueva_ont)
        print(f"Evaluación automática: {cal} ({puntos}/3)")

        reviewed_ont, human_feedback = human_review(nueva_ont)

        if reviewed_ont:
            actual_ont = reviewed_ont
        else:
            actual_ont = nueva_ont

        if human_feedback:
            actual_feedback = human_feedback
        elif puntos < 3:
            actual_feedback = "Refina clases, añade relaciones y más restricciones."
        else:
            actual_feedback = "Añade propiedades de datos y mejora semántica."

        with open(f"practica_final/v{i}_ontologia.json", "w", encoding="utf-8") as f:
            json.dump(actual_ont, f, indent=2, ensure_ascii=False)

        with open(f"practica_final/v{i}_feedback.txt", "w", encoding="utf-8") as f:
            f.write(actual_feedback or "")

    print("\nProceso completado. Resultados en 'practica_final'.")


# ==========================================================
# 8. ENTRYPOINT
# ==========================================================
if __name__ == "__main__":
    run()