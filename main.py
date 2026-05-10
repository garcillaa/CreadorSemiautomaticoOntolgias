import json
import os
import sys
from datetime import datetime

from config import get_llm
from generator import generate_ontology
from evaluator import evaluate, format_evaluation_report
from owl_exporter import ontology_to_owl, save_ontology, validate_with_sparql, sanitize_uri


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

    disjuntas = ontology.get("clases_disjuntas", [])
    if disjuntas:
        print(f"\n  Clases disjuntas ({len(disjuntas)} grupos):")
        for grupo in disjuntas:
            print(f"    - {' | '.join(grupo)}")

    obj_props = ontology.get("object_properties", [])
    print(f"\n  Object Properties ({len(obj_props)}):")
    for p in obj_props:
        inv = f" (inversa: {p['inversa']})" if p.get("inversa") and p["inversa"] != "null" else ""
        print(f"    - {p.get('nombre', '?')}: {p.get('dominio', '?')} -> {p.get('rango', '?')}{inv}")

    dt_props = ontology.get("datatype_properties", [])
    print(f"\n  Datatype Properties ({len(dt_props)}):")
    for p in dt_props:
        print(f"    - {p.get('nombre', '?')}: {p.get('dominio', '?')} [{p.get('rango', '?')}]")

    restricciones = ontology.get("restricciones", [])
    print(f"\n  Restricciones ({len(restricciones)}):")
    for r in restricciones:
        print(f"    - {r.get('clase', '?')}.{r.get('propiedad', '?')} {r.get('tipo', '?')} {r.get('valor', '?')}")

    reglas = ontology.get("reglas_swrl", [])
    if reglas:
        print(f"\n  Reglas SWRL ({len(reglas)}):")
        for r in reglas:
            print(f"    - {r.get('nombre', '?')}: {r.get('antecedente', '?')} -> {r.get('consecuente', '?')}")
            if r.get("descripcion"):
                print(f"      ({r['descripcion']})")

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

    safe_uri_domain = sanitize_uri(domain.lower().replace(" ", "_"))
    base_uri = f"http://example.org/ontology/{safe_uri_domain}#"

    current_ontology = None
    feedback = None
    iteration = 0

    print(f"\n  Directorio de salida: {output_dir}")
    print(f"  Namespace: {base_uri}")
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
        evaluation = evaluate(llm, new_ontology, questions, base_uri)
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
            graph = ontology_to_owl(new_ontology, domain, base_uri=base_uri)
            ttl_path, owl_path = save_ontology(graph, output_dir, "ontologia_final")
            print(f"  Guardado: {ttl_path}")
            print(f"  Guardado: {owl_path}")

            sem_evals = evaluation.get("semantica", {}).get("evaluaciones", [])
            print("\n  Validando consultas SPARQL contra el grafo...")
            sparql_results_log = []
            for ev in sem_evals:
                sparql = ev.get("sparql", "").strip()
                if not sparql:
                    print(f"    Sin SPARQL: {ev.get('pregunta', '?')[:60]}")
                    sparql_results_log.append({"pregunta": ev.get("pregunta"), "resultado": "sin consulta"})
                    continue

                if "PREFIX" not in sparql.upper():
                    sparql = f"PREFIX ont: <{base_uri}>\nPREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\nPREFIX owl: <http://www.w3.org/2002/07/owl#>\n{sparql}"

                results, error = validate_with_sparql(graph, sparql)
                pregunta_corta = ev.get('pregunta', '?')[:60]
                if error:
                    print(f"    SPARQL error ({pregunta_corta}): {error[:80]}")
                    sparql_results_log.append({"pregunta": ev.get("pregunta"), "error": error[:120]})
                else:
                    print(f"    OK: {pregunta_corta} -> {len(results)} resultados")
                    sparql_results_log.append({"pregunta": ev.get("pregunta"), "resultados": len(results)})

            sparql_log_path = os.path.join(output_dir, "sparql_validation.json")
            with open(sparql_log_path, "w", encoding="utf-8") as f:
                json.dump(sparql_results_log, f, indent=2, ensure_ascii=False)

            # Generar fichero de consultas listas para Protégé
            sparql_file_path = os.path.join(output_dir, "consultas_protege.sparql")
            with open(sparql_file_path, "w", encoding="utf-8") as f:
                f.write(f"# Consultas SPARQL para la ontología: {domain}\n")
                f.write(f"# Generadas automáticamente - copiar/pegar en Protégé (SPARQL Query tab)\n")
                f.write(f"# Namespace: {base_uri}\n")
                f.write(f"#\n")
                f.write(f"# INSTRUCCIONES PARA PROTÉGÉ:\n")
                f.write(f"#   1. Abrir el fichero .owl en Protégé\n")
                f.write(f"#   2. Activar el reasoner: Reasoner > HermiT > Start reasoner\n")
                f.write(f"#   3. Ir a la pestaña SPARQL Query (si no aparece: Window > Tabs > SPARQL Query)\n")
                f.write(f"#   4. Copiar cada consulta y ejecutarla\n")
                f.write(f"#\n")
                f.write(f"# CONSULTA GENERAL: Ver todas las instancias y sus clases\n\n")
                f.write(f"PREFIX ont: <{base_uri}>\n")
                f.write(f"PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n")
                f.write(f"PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n")
                f.write(f"PREFIX owl: <http://www.w3.org/2002/07/owl#>\n\n")
                f.write(f"SELECT ?instancia ?clase\n")
                f.write(f"WHERE {{\n")
                f.write(f"  ?instancia rdf:type ?clase .\n")
                f.write(f"  ?instancia rdf:type owl:NamedIndividual .\n")
                f.write(f"  FILTER (?clase != owl:NamedIndividual)\n")
                f.write(f"}}\n")

                for ev in sem_evals:
                    sparql = ev.get("sparql", "").strip()
                    if not sparql:
                        continue
                    pregunta = ev.get("pregunta", "Pregunta sin título")
                    resuelta = "RESUELTA" if ev.get("resuelta") else "NO RESUELTA"
                    f.write(f"\n{'#' * 60}\n")
                    f.write(f"# [{resuelta}] {pregunta}\n")
                    f.write(f"{'#' * 60}\n\n")
                    if "PREFIX" not in sparql.upper():
                        f.write(f"PREFIX ont: <{base_uri}>\n")
                        f.write(f"PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n")
                        f.write(f"PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n\n")
                    f.write(f"{sparql}\n")

            print(f"\n  Consultas SPARQL para Protégé: {sparql_file_path}")

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
