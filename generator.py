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

    base = f"""Actúa como un Ingeniero Ontológico Senior experto en OWL, RDF y SWRL.

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
  "clases_disjuntas": [
    ["Clase1", "Clase2", "Clase3"]
  ],
  "object_properties": [
    {{
      "nombre": "nombrePropiedad",
      "dominio": "ClaseDominio",
      "rango": "ClaseRango",
      "inversa": "nombrePropiedadInversa o null",
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
  "reglas_swrl": [
    {{
      "nombre": "NombreRegla",
      "descripcion": "Qué infiere esta regla",
      "antecedente": "Condiciones (ej: Alumno(?a) ^ cursaClase(?a, ?c) ^ Clase(?c))",
      "consecuente": "Conclusión (ej: perteneceAInstituto(?a, ?i))"
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

Requisitos OBLIGATORIOS:
- Las clases deben formar una jerarquía coherente con superclases.
- Las clases del mismo nivel jerárquico (hermanas) DEBEN declararse como disjuntas en "clases_disjuntas".
- CADA object_property DEBE tener su propiedad inversa. Ejemplo: si existe "imparte" (Profesor->Clase), debe existir "esImpartidaPor" (Clase->Profesor), y en el campo "inversa" de "imparte" poner "esImpartidaPor" y viceversa.
- Incluye datatype_properties para atributos literales (nombres, fechas, cantidades, etc.).
- Las restricciones deben ser formales (tipo OWL) y relevantes para responder las preguntas.
- Las reglas SWRL deben permitir inferir conocimiento nuevo a partir de los datos existentes. Escribe al menos una regla SWRL por cada pregunta de competencia que implique razonamiento transitivo o combinación de relaciones.
- En las reglas SWRL usa EXACTAMENTE los nombres de clases y propiedades que hayas definido arriba.
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
