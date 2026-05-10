import json
from owl_exporter import sanitize_uri


# ==========================================================
# 1. PROMPT PARA EL LLM
#    Solo le pedimos QUÉ NECESITA cada pregunta.
#    La verificación de si existe o no la hacemos nosotros.
# ==========================================================
def build_mapping_prompt(ontology, questions):
    """Prompt para que el LLM mapee cada pregunta a clases y propiedades necesarias."""
    questions_str = "\n".join(f"  {i+1}. {q}" for i, q in enumerate(questions))

    clases = list(ontology.get("clases", {}).keys())
    obj_props = [p["nombre"] for p in ontology.get("object_properties", [])]
    dt_props = [p["nombre"] for p in ontology.get("datatype_properties", [])]

    return f"""Eres un experto en ontologías. Tu ÚNICA tarea es determinar qué clases y propiedades
se necesitan para responder cada pregunta de competencia.

Clases que EXISTEN en la ontología: {clases}
Object Properties que EXISTEN: {obj_props}
Datatype Properties que EXISTEN: {dt_props}

Preguntas de competencia:
{questions_str}

Para CADA pregunta, indica:
- Qué clases se necesitan para responderla (usa SOLO nombres de la lista de arriba)
- Qué propiedades (object o datatype) se necesitan (usa SOLO nombres de la lista de arriba)
- Si necesitas alguna clase o propiedad que NO existe en las listas, inclúyela en "elementos_faltantes"

NO evalúes si la pregunta está resuelta o no. Solo haz el mapeo.

Responde ÚNICAMENTE con JSON:
{{
  "mapeo": [
    {{
      "pregunta": "La pregunta original",
      "clases_necesarias": ["Clase1", "Clase2"],
      "propiedades_necesarias": ["prop1", "prop2"],
      "elementos_faltantes": ["nombre de clase o propiedad que no existe pero se necesita"]
    }}
  ]
}}

RESPONDE ÚNICAMENTE CON JSON."""


# ==========================================================
# 2. VERIFICACIÓN PROGRAMÁTICA
#    Comprueba con código si lo que el LLM dice que se
#    necesita realmente existe en la ontología.
# ==========================================================
def verify_question_coverage(mapping_entry, ontology):
    """Verifica programáticamente si una pregunta está cubierta por la ontología."""
    clases_ont = set(ontology.get("clases", {}).keys())
    obj_prop_names = {p["nombre"] for p in ontology.get("object_properties", [])}
    dt_prop_names = {p["nombre"] for p in ontology.get("datatype_properties", [])}
    all_prop_names = obj_prop_names | dt_prop_names

    # También contar las inversas como propiedades existentes
    for p in ontology.get("object_properties", []):
        inv = p.get("inversa")
        if inv and inv != "null":
            all_prop_names.add(inv)
            obj_prop_names.add(inv)

    clases_necesarias = mapping_entry.get("clases_necesarias", [])
    props_necesarias = mapping_entry.get("propiedades_necesarias", [])
    elementos_faltantes_llm = mapping_entry.get("elementos_faltantes", [])

    # Verificar clases
    clases_presentes = [c for c in clases_necesarias if c in clases_ont]
    clases_faltantes = [c for c in clases_necesarias if c not in clases_ont]

    # Verificar propiedades
    props_presentes = [p for p in props_necesarias if p in all_prop_names]
    props_faltantes = [p for p in props_necesarias if p not in all_prop_names]

    # Verificar que las propiedades conectan las clases necesarias
    obj_props_dict = {}
    for p in ontology.get("object_properties", []):
        obj_props_dict[p["nombre"]] = (p.get("dominio", ""), p.get("rango", ""))
        inv = p.get("inversa")
        if inv and inv != "null":
            obj_props_dict[inv] = (p.get("rango", ""), p.get("dominio", ""))

    conexiones_validas = True
    conexiones_detalle = []
    for prop_name in props_necesarias:
        if prop_name in obj_props_dict:
            dom, ran = obj_props_dict[prop_name]
            conexiones_detalle.append(f"{prop_name}: {dom} -> {ran}")
        elif prop_name in dt_prop_names:
            for dp in ontology.get("datatype_properties", []):
                if dp["nombre"] == prop_name:
                    conexiones_detalle.append(f"{prop_name}: {dp.get('dominio', '?')} -> {dp.get('rango', '?')}")
                    break

    # Calcular elementos realmente faltantes
    todos_faltantes = []
    for c in clases_faltantes:
        todos_faltantes.append(f"Clase: {c}")
    for p in props_faltantes:
        todos_faltantes.append(f"Propiedad: {p}")
    # Añadir lo que el LLM detectó como faltante si realmente no existe
    for elem in elementos_faltantes_llm:
        elem_clean = elem.strip()
        if elem_clean and elem_clean not in clases_ont and elem_clean not in all_prop_names:
            if f"Clase: {elem_clean}" not in todos_faltantes and f"Propiedad: {elem_clean}" not in todos_faltantes:
                todos_faltantes.append(elem_clean)

    resuelta = len(todos_faltantes) == 0 and len(clases_necesarias) > 0

    return {
        "pregunta": mapping_entry.get("pregunta", ""),
        "resuelta": resuelta,
        "clases_necesarias": clases_necesarias,
        "clases_presentes": clases_presentes,
        "clases_faltantes": clases_faltantes,
        "propiedades_necesarias": props_necesarias,
        "propiedades_presentes": props_presentes,
        "propiedades_faltantes": props_faltantes,
        "conexiones": conexiones_detalle,
        "elementos_faltantes": todos_faltantes,
        "justificacion": _build_justification(resuelta, todos_faltantes, conexiones_detalle)
    }


def _build_justification(resuelta, faltantes, conexiones):
    """Genera una justificación legible automáticamente."""
    if resuelta:
        if conexiones:
            return f"Resuelta. Camino: {' + '.join(conexiones)}"
        return "Resuelta. Todas las clases y propiedades necesarias existen."
    else:
        return f"No resuelta. Falta: {', '.join(faltantes)}"


# ==========================================================
# 3. GENERADOR PROGRAMÁTICO DE SPARQL
# ==========================================================
def generate_sparql_for_question(verified_entry, ontology, base_uri):
    """Genera SPARQL programáticamente para preguntas resueltas."""
    if not verified_entry.get("resuelta"):
        return None

    clases_necesarias = verified_entry.get("clases_necesarias", [])
    props_necesarias = verified_entry.get("propiedades_necesarias", [])

    clases_ont = set(ontology.get("clases", {}).keys())
    obj_props = {}
    for p in ontology.get("object_properties", []):
        obj_props[p["nombre"]] = p
        inv = p.get("inversa")
        if inv and inv != "null":
            obj_props[inv] = {
                "nombre": inv,
                "dominio": p.get("rango", ""),
                "rango": p.get("dominio", "")
            }
    dt_props = {p["nombre"]: p for p in ontology.get("datatype_properties", [])}

    clases_validas = [c for c in clases_necesarias if c in clases_ont]
    if not clases_validas:
        return None

    prefix = f"PREFIX ont: <{base_uri}>\nPREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
    triples = []
    variables = []

    for clase in clases_validas:
        var = f"?{sanitize_uri(clase.lower())}"
        variables.append(var)
        triples.append(f"  {var} rdf:type ont:{sanitize_uri(clase)} .")

    for prop_name in props_necesarias:
        if prop_name in obj_props:
            prop = obj_props[prop_name]
            dominio = prop.get("dominio", "")
            rango = prop.get("rango", "")
            var_dom = f"?{sanitize_uri(dominio.lower())}" if dominio in clases_ont else None
            var_ran = f"?{sanitize_uri(rango.lower())}" if rango in clases_ont else None
            if var_dom and var_ran:
                triples.append(f"  {var_dom} ont:{sanitize_uri(prop_name)} {var_ran} .")
        elif prop_name in dt_props:
            prop = dt_props[prop_name]
            dominio = prop.get("dominio", "")
            var_dom = f"?{sanitize_uri(dominio.lower())}" if dominio in clases_ont else None
            var_val = f"?val_{sanitize_uri(prop_name)}"
            if var_dom:
                variables.append(var_val)
                triples.append(f"  {var_dom} ont:{sanitize_uri(prop_name)} {var_val} .")

    if not triples:
        return None

    variables = list(dict.fromkeys(variables))
    select_vars = " ".join(variables)
    body = "\n".join(triples)
    return f"{prefix}SELECT {select_vars}\nWHERE {{\n{body}\n}}"


# ==========================================================
# 4. EVALUACIÓN ESTRUCTURAL (sin LLM)
# ==========================================================
def build_structural_evaluation(ontology):
    """Evaluación estructural sin LLM: métricas objetivas."""
    results = {
        "num_clases": 0,
        "num_object_properties": 0,
        "num_datatype_properties": 0,
        "num_restricciones": 0,
        "num_instancias": 0,
        "num_reglas_swrl": 0,
        "tiene_jerarquia": False,
        "tiene_disjuntas": False,
        "tiene_inversas": False,
        "clases_aisladas": [],
    }

    if not ontology:
        return results

    clases = ontology.get("clases", {})
    obj_props = ontology.get("object_properties", [])
    dt_props = ontology.get("datatype_properties", [])
    restricciones = ontology.get("restricciones", [])
    instancias = ontology.get("instancias_ejemplo", [])
    reglas = ontology.get("reglas_swrl", [])
    disjuntas = ontology.get("clases_disjuntas", [])

    results["num_clases"] = len(clases)
    results["num_object_properties"] = len(obj_props)
    results["num_datatype_properties"] = len(dt_props)
    results["num_restricciones"] = len(restricciones)
    results["num_instancias"] = len(instancias)
    results["num_reglas_swrl"] = len(reglas)
    results["tiene_disjuntas"] = len(disjuntas) > 0

    for clase_info in clases.values():
        if isinstance(clase_info, dict) and clase_info.get("superclase"):
            results["tiene_jerarquia"] = True
            break

    for prop in obj_props:
        if prop.get("inversa") and prop["inversa"] != "null":
            results["tiene_inversas"] = True
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


# ==========================================================
# 5. EVALUACIÓN COMPLETA
# ==========================================================
def evaluate(llm, ontology, questions, base_uri=None):
    """Evaluación completa: estructural + semántica con verificación programática."""
    if not base_uri:
        base_uri = "http://example.org/ontology/default#"

    structural = build_structural_evaluation(ontology)

    # Paso 1: LLM mapea preguntas a clases/propiedades necesarias
    prompt = build_mapping_prompt(ontology, questions)
    response = llm.invoke(prompt)

    try:
        start = response.content.find("{")
        end = response.content.rfind("}") + 1
        llm_mapping = json.loads(response.content[start:end])
    except (json.JSONDecodeError, ValueError):
        llm_mapping = {"mapeo": []}

    # Paso 2: Verificación PROGRAMÁTICA de cada pregunta
    evaluaciones = []
    for mapping_entry in llm_mapping.get("mapeo", []):
        verified = verify_question_coverage(mapping_entry, ontology)
        sparql = generate_sparql_for_question(verified, ontology, base_uri)
        verified["sparql"] = sparql or ""
        evaluaciones.append(verified)

    # Calcular puntuación
    resueltas = sum(1 for e in evaluaciones if e["resuelta"])
    total = len(evaluaciones) if evaluaciones else 1
    puntuacion = resueltas / total

    semantic = {
        "evaluaciones": evaluaciones,
        "puntuacion_global": puntuacion,
        "resumen": f"{resueltas}/{total} preguntas resueltas."
    }

    return {
        "estructural": structural,
        "semantica": semantic,
        "puntuacion_competencia": puntuacion
    }


# ==========================================================
# 6. FORMATO DE INFORME
# ==========================================================
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
    lines.append(f"    Reglas SWRL:         {st['num_reglas_swrl']}")
    lines.append(f"    Instancias ejemplo:  {st['num_instancias']}")
    lines.append(f"    Jerarquía:           {'Sí' if st['tiene_jerarquia'] else 'No'}")
    lines.append(f"    Clases disjuntas:    {'Sí' if st['tiene_disjuntas'] else 'No'}")
    lines.append(f"    Propiedades inversas:{'Sí' if st['tiene_inversas'] else 'No'}")

    if st["clases_aisladas"]:
        lines.append(f"    Clases aisladas:     {', '.join(st['clases_aisladas'])}")

    sem = evaluation["semantica"]
    score = evaluation["puntuacion_competencia"]
    lines.append(f"\n  [Preguntas de competencia] — {score:.0%}")

    for ev in sem.get("evaluaciones", []):
        status = "✓ RESUELTA" if ev.get("resuelta") else "✗ NO RESUELTA"
        lines.append(f"\n    [{status}] {ev.get('pregunta', '?')}")

        if ev.get("conexiones"):
            lines.append(f"      Camino: {' + '.join(ev['conexiones'])}")

        if ev.get("elementos_faltantes"):
            lines.append(f"      Falta:  {', '.join(ev['elementos_faltantes'])}")

        lines.append(f"      {ev.get('justificacion', '')}")

        if ev.get("sparql"):
            sparql_lines = ev["sparql"].split("\n")
            for sl in sparql_lines:
                s = sl.strip()
                if s.startswith("SELECT") or s.startswith("WHERE") or s.startswith("?"):
                    lines.append(f"      {s}")

    lines.append(f"\n  Resumen: {sem.get('resumen', '')}")
    lines.append("=" * 60)
    return "\n".join(lines)
