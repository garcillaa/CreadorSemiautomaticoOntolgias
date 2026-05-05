import json
import os
import sys
from datetime import datetime

from config import get_llm
from generator import generate_ontology
from evaluator import evaluate, format_evaluation_report
from owl_exporter import ontology_to_owl, save_ontology, validate_with_sparql


def print_header():
    print("\n" + "=" * 60)
    print("  CONSTRUCCIÓN SEMIAUTOMÁTICA DE ONTOLOGÍAS CON LLMs")
    print("=" * 60)


def get_domain_config():
    """Solicita al usuario la configuración del dominio."""
    print("\n--- Configuración del dominio ---\n")

    domain = input("  Dominio de la ontología: ").strip()
    while not domain:
        domain = input("  (obligatorio) Dominio: ").strip()

    objective = input("  Objetivo/descripción: ").strip()
    while not objective:
        objective = input("  (obligatorio) Objetivo: ").strip()

    print("\n  Introduce las preguntas de competencia (escribe 'fin' para terminar):")
    questions = []
    while True:
        q = input(f"    Pregunta {len(questions) + 1}: ").strip()
        if q.lower() == "fin":
            break
        if q:
            questions.append(q)

    while len(questions) < 1:
        print("  Necesitas al menos una pregunta de competencia.")
        q = input("    Pregunta 1: ").strip()
        if q:
            questions.append(q)

    return domain, objective, questions


def display_ontology(ontology):
    """Muestra la ontología de forma legible."""
    print("\n--- Ontología generada ---\n")

    clases = ontology.get("clases", {})
    print(f"  Clases ({len(clases)}):")
    for nombre, info in clases.items():
        if isinstance(info, dict):
            sup = f" -> {info.get('superclase', '')}" if info.get("superclase") else ""
            print(f"    - {nombre}{sup}: {info.get('definicion', '')}")
        else:
            print(f"    - {nombre}: {info}")

    obj_props = ontology.get("object_properties", [])
    print(f"\n  Object Properties ({len(obj_props)}):")
    for p in obj_props:
        print(f"    - {p.get('nombre', '?')}: {p.get('dominio', '?')} -> {p.get('rango', '?')}")

    dt_props = ontology.get("datatype_properties", [])
    print(f"\n  Datatype Properties ({len(dt_props)}):")
    for p in dt_props:
        print(f"    - {p.get('nombre', '?')}: {p.get('dominio', '?')} [{p.get('rango', '?')}]")

    restricciones = ontology.get("restricciones", [])
    print(f"\n  Restricciones ({len(restricciones)}):")
    for r in restricciones:
        print(f"    - {r.get('clase', '?')}.{r.get('propiedad', '?')} {r.get('tipo', '?')} {r.get('valor', '?')}")

    instancias = ontology.get("instancias_ejemplo", [])
    print(f"\n  Instancias ejemplo ({len(instancias)}):")
    for inst in instancias:
        print(f"    - {inst.get('nombre', '?')} (tipo: {inst.get('clase', '?')})")


def human_review():
    """Solicita la decisión del usuario sobre la iteración actual."""
    print("\n--- Revisión ---")
    print("  [a] Aceptar esta versión como FINAL")
    print("  [r] Refinar con feedback (nueva iteración)")
    print("  [v] Ver JSON completo")
    print("  [q] Salir sin guardar versión final")

    while True:
        choice = input("\n  Tu decisión: ").strip().lower()
        if choice in ("a", "r", "v", "q"):
            return choice
        print("  Opción no válida. Usa: a, r, v, q")


def run():
    print_header()

    llm = get_llm()
    domain, objective, questions = get_domain_config()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_domain = domain.lower().replace(" ", "_")[:30]
    output_dir = os.path.join("output", f"{safe_domain}_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)

    session_log = {
        "dominio": domain,
        "objetivo": objective,
        "preguntas_competencia": questions,
        "iteraciones": []
    }

    current_ontology = None
    feedback = None
    iteration = 0

    print(f"\n  Directorio de salida: {output_dir}")
    print("  Iniciando generación iterativa...\n")

    while True:
        iteration += 1
        print(f"\n{'=' * 60}")
        print(f"  ITERACIÓN {iteration}")
        print(f"{'=' * 60}")

        print("\n  Generando ontología con el LLM...")
        new_ontology = generate_ontology(
            llm, domain, objective, questions,
            previous=current_ontology, feedback=feedback
        )

        if not new_ontology:
            print("  ERROR: El LLM no generó un JSON válido.")
            retry = input("  ¿Reintentar esta iteración? (s/n): ").strip().lower()
            if retry == "s":
                iteration -= 1
                continue
            else:
                break

        display_ontology(new_ontology)

        print("\n  Evaluando calidad...")
        evaluation = evaluate(llm, new_ontology, questions)
        print(format_evaluation_report(evaluation))

        version_file = os.path.join(output_dir, f"v{iteration}_ontologia.json")
        with open(version_file, "w", encoding="utf-8") as f:
            json.dump(new_ontology, f, indent=2, ensure_ascii=False)

        eval_file = os.path.join(output_dir, f"v{iteration}_evaluacion.json")
        with open(eval_file, "w", encoding="utf-8") as f:
            json.dump(evaluation, f, indent=2, ensure_ascii=False)

        iter_log = {
            "version": iteration,
            "feedback_entrada": feedback,
            "puntuacion": evaluation.get("puntuacion_competencia", 0),
        }

        decision = human_review()

        if decision == "v":
            print(json.dumps(new_ontology, indent=2, ensure_ascii=False))
            decision = human_review()

        if decision == "a":
            current_ontology = new_ontology
            iter_log["decision"] = "aceptada"
            session_log["iteraciones"].append(iter_log)

            print("\n  Exportando a OWL/Turtle...")
            graph = ontology_to_owl(new_ontology, domain)
            ttl_path, owl_path = save_ontology(graph, output_dir, "ontologia_final")
            print(f"  Guardado: {ttl_path}")
            print(f"  Guardado: {owl_path}")

            sem_evals = evaluation.get("semantica", {}).get("evaluaciones", [])
            print("\n  Validando consultas SPARQL contra el grafo...")
            for ev in sem_evals:
                sparql = ev.get("sparql", "")
                if sparql:
                    results, error = validate_with_sparql(graph, sparql)
                    if error:
                        print(f"    SPARQL error: {error[:80]}")
                    else:
                        print(f"    Pregunta: {ev.get('pregunta', '?')[:50]}... -> {len(results)} resultados")

            break

        elif decision == "r":
            feedback = input("\n  Tu feedback para la siguiente iteración: ").strip()
            if not feedback:
                feedback = "Mejora la cobertura de las preguntas de competencia no resueltas."
            current_ontology = new_ontology
            iter_log["decision"] = "refinar"
            iter_log["feedback_salida"] = feedback
            session_log["iteraciones"].append(iter_log)

        elif decision == "q":
            iter_log["decision"] = "abandonada"
            session_log["iteraciones"].append(iter_log)
            print("\n  Sesión terminada sin versión final.")
            break

    log_path = os.path.join(output_dir, "session_log.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(session_log, f, indent=2, ensure_ascii=False)

    print(f"\n  Log de sesión guardado en: {log_path}")
    print("\n  Proceso finalizado.")


if __name__ == "__main__":
    run()
