import json


def extract_json(text):
    """Extrae el primer objeto JSON válido de un texto."""
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except (json.JSONDecodeError, ValueError):
        return None


def build_generation_prompt(domain, objective, questions, previous=None, feedback=None):
    questions_str = "\n".join(f"  - {q}" for q in questions)

    base = f"""Actúa como un Ingeniero Ontológico Senior experto en OWL y RDF.

Dominio: {domain}
Objetivo: {objective}

La ontología DEBE poder responder estas preguntas de competencia:
{questions_str}

Genera una ontología completa en JSON con EXACTAMENTE esta estructura:
{{
  "clases": {{
    "NombreClase": {{
      "definicion": "Descripción de la clase",
      "superclase": "NombreClasePadre o null"
    }}
  }},
  "object_properties": [
    {{
      "nombre": "nombrePropiedad",
      "dominio": "ClaseDominio",
      "rango": "ClaseRango",
      "descripcion": "Qué representa esta relación"
    }}
  ],
  "datatype_properties": [
    {{
      "nombre": "nombrePropiedad",
      "dominio": "ClaseDominio",
      "rango": "xsd:string | xsd:integer | xsd:float | xsd:boolean | xsd:dateTime",
      "descripcion": "Qué representa este atributo"
    }}
  ],
  "restricciones": [
    {{
      "clase": "NombreClase",
      "tipo": "someValuesFrom | allValuesFrom | minCardinality | maxCardinality | exactCardinality | hasValue",
      "propiedad": "nombrePropiedad",
      "valor": "valor o clase destino",
      "descripcion": "Explicación de la restricción"
    }}
  ],
  "instancias_ejemplo": [
    {{
      "nombre": "nombreInstancia",
      "clase": "NombreClase",
      "propiedades": {{ "prop": "valor" }}
    }}
  ]
}}

Requisitos:
- Las clases deben formar una jerarquía coherente con superclases.
- Debe haber suficientes object_properties para conectar todas las clases relevantes.
- Incluye datatype_properties para atributos literales (nombres, fechas, cantidades, etc.).
- Las restricciones deben ser formales (tipo OWL) y relevantes para responder las preguntas.
- Incluye al menos 3 instancias de ejemplo para verificar las preguntas de competencia.
- Asegúrate de que CADA pregunta de competencia se pueda responder con la estructura generada.
"""

    if previous:
        base += f"\nMEJORA esta versión anterior (no empieces de cero, refínala):\n{json.dumps(previous, ensure_ascii=False, indent=2)}\n"

    if feedback:
        base += f"\nFeedback del usuario que DEBES incorporar:\n{feedback}\n"

    base += "\nRESPONDE ÚNICAMENTE CON EL JSON. Sin explicaciones adicionales."
    return base


def generate_ontology(llm, domain, objective, questions, previous=None, feedback=None):
    prompt = build_generation_prompt(domain, objective, questions, previous, feedback)
    response = llm.invoke(prompt)
    return extract_json(response.content)
