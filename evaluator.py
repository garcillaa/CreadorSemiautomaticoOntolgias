import json


def build_evaluation_prompt(ontology, questions):
    """Construye el prompt para que el LLM evalúe las preguntas de competencia."""
    questions_str = "\n".join(f"  {i+1}. {q}" for i, q in enumerate(questions))
    ont_str = json.dumps(ontology, ensure_ascii=False, indent=2)

    return f"""Actúa como un evaluador experto en ontologías OWL.

Dada la siguiente ontología:
{ont_str}

Y las siguientes preguntas de competencia:
{questions_str}

Para CADA pregunta, evalúa:
1. ¿La ontología tiene las clases y propiedades necesarias para responderla?
2. Genera una consulta SPARQL que respondería esa pregunta SI la ontología estuviera en RDF/OWL.
3. Indica si la consulta es ejecutable con la estructura actual (sí/no) y por qué.

Responde ÚNICAMENTE con JSON en esta estructura:
{{
  "evaluaciones": [
    {{
      "pregunta": "La pregunta original",
      "resuelta": true/false,
      "sparql": "SELECT ... WHERE {{ ... }}",
      "clases_necesarias": ["clase1", "clase2"],
      "propiedades_necesarias": ["prop1", "prop2"],
      "clases_presentes": ["las que existen en la ontología"],
      "propiedades_presentes": ["las que existen"],
      "elementos_faltantes": ["lo que falta para resolverla"],
      "justificacion": "Explicación breve"
    }}
  ],
  "puntuacion_global": 0.0,
  "resumen": "Resumen general de la cobertura"
}}

La puntuacion_global es un float entre 0.0 y 1.0 (proporción de preguntas resueltas).
RESPONDE ÚNICAMENTE CON JSON."""


def build_structural_evaluation(ontology):
    """Evaluación estructural sin LLM: métricas objetivas."""
    results = {
        "num_clases": 0,
        "num_object_properties": 0,
        "num_datatype_properties": 0,
        "num_restricciones": 0,
        "num_instancias": 0,
        "tiene_jerarquia": False,
        "clases_sin_propiedades": [],
        "clases_aisladas": [],
    }

    if not ontology:
        return results

    clases = ontology.get("clases", {})
    obj_props = ontology.get("object_properties", [])
    dt_props = ontology.get("datatype_properties", [])
    restricciones = ontology.get("restricciones", [])
    instancias = ontology.get("instancias_ejemplo", [])

    results["num_clases"] = len(clases)
    results["num_object_properties"] = len(obj_props)
    results["num_datatype_properties"] = len(dt_props)
    results["num_restricciones"] = len(restricciones)
    results["num_instancias"] = len(instancias)

    for clase_info in clases.values():
        if isinstance(clase_info, dict) and clase_info.get("superclase"):
            results["tiene_jerarquia"] = True
            break

    clases_conectadas = set()
    for prop in obj_props:
        clases_conectadas.add(prop.get("dominio", ""))
        clases_conectadas.add(prop.get("rango", ""))
    for prop in dt_props:
        clases_conectadas.add(prop.get("dominio", ""))

    for nombre_clase in clases:
        if nombre_clase not in clases_conectadas:
            results["clases_aisladas"].append(nombre_clase)

    return results


def evaluate_competency(llm, ontology, questions):
    """Evaluación semántica usando el LLM para verificar preguntas de competencia."""
    prompt = build_evaluation_prompt(ontology, questions)
    response = llm.invoke(prompt)

    try:
        start = response.content.find("{")
        end = response.content.rfind("}") + 1
        return json.loads(response.content[start:end])
    except (json.JSONDecodeError, ValueError):
        return {
            "evaluaciones": [],
            "puntuacion_global": 0.0,
            "resumen": "Error al parsear la evaluación del LLM."
        }


def evaluate(llm, ontology, questions):
    """Evaluación completa: estructural + semántica."""
    structural = build_structural_evaluation(ontology)
    semantic = evaluate_competency(llm, ontology, questions)
    return {
        "estructural": structural,
        "semantica": semantic,
        "puntuacion_competencia": semantic.get("puntuacion_global", 0.0)
    }


def format_evaluation_report(evaluation):
    """Formatea el resultado de la evaluación para mostrar al usuario."""
    lines = []
    lines.append("\n" + "=" * 60)
    lines.append("  INFORME DE EVALUACIÓN")
    lines.append("=" * 60)

    st = evaluation["estructural"]
    lines.append(f"\n  [Métricas estructurales]")
    lines.append(f"    Clases:              {st['num_clases']}")
    lines.append(f"    Object Properties:   {st['num_object_properties']}")
    lines.append(f"    Datatype Properties: {st['num_datatype_properties']}")
    lines.append(f"    Restricciones:       {st['num_restricciones']}")
    lines.append(f"    Instancias ejemplo:  {st['num_instancias']}")
    lines.append(f"    Jerarquía de clases: {'Sí' if st['tiene_jerarquia'] else 'No'}")

    if st["clases_aisladas"]:
        lines.append(f"    Clases aisladas:     {', '.join(st['clases_aisladas'])}")

    sem = evaluation["semantica"]
    score = evaluation["puntuacion_competencia"]
    lines.append(f"\n  [Preguntas de competencia] — Puntuación: {score:.0%}")

    for ev in sem.get("evaluaciones", []):
        status = "RESUELTA" if ev.get("resuelta") else "NO RESUELTA"
        lines.append(f"\n    [{status}] {ev.get('pregunta', '?')}")
        if ev.get("sparql"):
            lines.append(f"      SPARQL: {ev['sparql'][:100]}...")
        if ev.get("elementos_faltantes"):
            lines.append(f"      Falta:  {', '.join(ev['elementos_faltantes'])}")

    if sem.get("resumen"):
        lines.append(f"\n  Resumen: {sem['resumen']}")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)
