import os
import re
from rdflib import Graph, Namespace, Literal, URIRef, BNode
from rdflib.namespace import RDF, RDFS, OWL, XSD
from rdflib.collection import Collection


# ==========================================================
# CONSTANTES
# ==========================================================
XSD_MAP = {
    "xsd:string": XSD.string,
    "xsd:integer": XSD.integer,
    "xsd:int": XSD.integer,
    "xsd:float": XSD.float,
    "xsd:double": XSD.double,
    "xsd:boolean": XSD.boolean,
    "xsd:dateTime": XSD.dateTime,
    "xsd:date": XSD.date,
}

SWRL = Namespace("http://www.w3.org/2003/11/swrl#")
SWRLB = Namespace("http://www.w3.org/2003/11/swrlb#")


def sanitize_uri(name):
    """Convierte un nombre a un fragmento URI válido."""
    return (name.replace(" ", "_")
            .replace("á", "a").replace("é", "e")
            .replace("í", "i").replace("ó", "o")
            .replace("ú", "u").replace("ñ", "n")
            .replace("Á", "A").replace("É", "E")
            .replace("Í", "I").replace("Ó", "O")
            .replace("Ú", "U").replace("Ñ", "N"))


def _find_class_fuzzy(name, clases):
    """Busca una clase por nombre exacto o insensible a mayúsculas."""
    if not name:
        return None
    if name in clases:
        return name
    name_lower = name.lower()
    for c in clases:
        if c.lower() == name_lower:
            return c
    return None


# ==========================================================
# CONVERSIÓN JSON -> GRAFO OWL
# ==========================================================
def ontology_to_owl(ontology, domain_name, base_uri=None):
    """Convierte la ontología JSON a un grafo RDF/OWL completo."""
    if not base_uri:
        safe_domain = sanitize_uri(domain_name.lower().replace(" ", "_"))
        base_uri = f"http://example.org/ontology/{safe_domain}#"

    g = Graph()
    ns = Namespace(base_uri)
    g.bind("ont", ns)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)
    g.bind("xsd", XSD)
    g.bind("swrl", SWRL)
    g.bind("swrlb", SWRLB)

    ont_uri = URIRef(base_uri.rstrip("#"))
    g.add((ont_uri, RDF.type, OWL.Ontology))
    g.add((ont_uri, RDFS.label, Literal(f"Ontología: {domain_name}")))

    clases = ontology.get("clases", {})

    # --- Clases ---
    for nombre_clase, info in clases.items():
        clase_uri = ns[sanitize_uri(nombre_clase)]
        g.add((clase_uri, RDF.type, OWL.Class))

        if isinstance(info, dict):
            if info.get("definicion"):
                g.add((clase_uri, RDFS.comment, Literal(info["definicion"])))
            superclase_raw = info.get("superclase")
            if superclase_raw and superclase_raw != "null":
                superclase = _find_class_fuzzy(superclase_raw, clases)
                if superclase:
                    g.add((clase_uri, RDFS.subClassOf, ns[sanitize_uri(superclase)]))
        elif isinstance(info, str):
            g.add((clase_uri, RDFS.comment, Literal(info)))

    # --- Clases disjuntas ---
    # 1) Las que el LLM declaró explícitamente
    grupos_disjuntos = list(ontology.get("clases_disjuntas", []))

    # 2) AUTO-DETECTAR clases hermanas (mismo padre, o todas raíz) -> disjuntas
    hijos_por_padre = {}  # padre -> [hijos]
    raices = []
    for nombre_clase, info in clases.items():
        if isinstance(info, dict):
            padre = info.get("superclase")
            if padre and padre != "null":
                padre_match = _find_class_fuzzy(padre, clases)
                if padre_match:
                    hijos_por_padre.setdefault(padre_match, []).append(nombre_clase)
                else:
                    raices.append(nombre_clase)
            else:
                raices.append(nombre_clase)
        else:
            raices.append(nombre_clase)

    for hermanos in hijos_por_padre.values():
        if len(hermanos) >= 2:
            grupos_disjuntos.append(hermanos)
    if len(raices) >= 2:
        grupos_disjuntos.append(raices)

    # 3) Aplicar todos los grupos disjuntos (deduplicando pares)
    pares_disjuntos = set()
    for grupo in grupos_disjuntos:
        if not isinstance(grupo, list) or len(grupo) < 2:
            continue
        uris_validas = []
        for c in grupo:
            matched = _find_class_fuzzy(c, clases)
            if matched and matched not in [u for u in uris_validas]:
                uris_validas.append(matched)
        for i in range(len(uris_validas)):
            for j in range(i + 1, len(uris_validas)):
                par = tuple(sorted([uris_validas[i], uris_validas[j]]))
                if par not in pares_disjuntos:
                    pares_disjuntos.add(par)
                    g.add((ns[sanitize_uri(par[0])], OWL.disjointWith, ns[sanitize_uri(par[1])]))

    # --- Construir mapa de inversas para asignar domain/range ---
    inverse_map = {}  # nombre_inversa -> {dominio, rango} (invertidos)
    for prop in ontology.get("object_properties", []):
        inversa = prop.get("inversa")
        if inversa and inversa != "null":
            dom = _find_class_fuzzy(prop.get("dominio", ""), clases)
            ran = _find_class_fuzzy(prop.get("rango", ""), clases)
            if dom and ran:
                inverse_map[inversa] = {"dominio": ran, "rango": dom}

    # --- Object Properties (con inversas completas) ---
    inversas_registradas = set()
    for prop in ontology.get("object_properties", []):
        prop_nombre = prop.get("nombre", "")
        prop_uri = ns[sanitize_uri(prop_nombre)]
        g.add((prop_uri, RDF.type, OWL.ObjectProperty))

        if prop.get("descripcion"):
            g.add((prop_uri, RDFS.comment, Literal(prop["descripcion"])))

        dom = _find_class_fuzzy(prop.get("dominio", ""), clases)
        ran = _find_class_fuzzy(prop.get("rango", ""), clases)
        if dom:
            g.add((prop_uri, RDFS.domain, ns[sanitize_uri(dom)]))
        if ran:
            g.add((prop_uri, RDFS.range, ns[sanitize_uri(ran)]))

        inversa = prop.get("inversa")
        if inversa and inversa != "null":
            inv_uri = ns[sanitize_uri(inversa)]
            par = tuple(sorted([prop_nombre, inversa]))
            if par not in inversas_registradas:
                g.add((prop_uri, OWL.inverseOf, inv_uri))
                g.add((inv_uri, RDF.type, OWL.ObjectProperty))
                # Asignar domain/range invertidos a la propiedad inversa
                if ran:
                    g.add((inv_uri, RDFS.domain, ns[sanitize_uri(ran)]))
                if dom:
                    g.add((inv_uri, RDFS.range, ns[sanitize_uri(dom)]))
                inversas_registradas.add(par)

    # --- Datatype Properties ---
    for prop in ontology.get("datatype_properties", []):
        prop_uri = ns[sanitize_uri(prop["nombre"])]
        g.add((prop_uri, RDF.type, OWL.DatatypeProperty))

        if prop.get("descripcion"):
            g.add((prop_uri, RDFS.comment, Literal(prop["descripcion"])))

        dom = _find_class_fuzzy(prop.get("dominio", ""), clases)
        if dom:
            g.add((prop_uri, RDFS.domain, ns[sanitize_uri(dom)]))

        rango = prop.get("rango", "xsd:string")
        xsd_type = XSD_MAP.get(rango, XSD.string)
        g.add((prop_uri, RDFS.range, xsd_type))

    # --- Restricciones OWL ---
    for rest in ontology.get("restricciones", []):
        clase_nombre_raw = rest.get("clase", "")
        clase_nombre = _find_class_fuzzy(clase_nombre_raw, clases)
        if not clase_nombre:
            continue

        clase_uri = ns[sanitize_uri(clase_nombre)]
        tipo = rest.get("tipo", "")
        propiedad = rest.get("propiedad", "")
        valor = rest.get("valor", "")

        if not propiedad:
            continue

        prop_uri = ns[sanitize_uri(propiedad)]
        restriction = BNode()
        g.add((restriction, RDF.type, OWL.Restriction))
        g.add((restriction, OWL.onProperty, prop_uri))

        valor_clase = _find_class_fuzzy(valor, clases) if isinstance(valor, str) else None

        if tipo == "someValuesFrom" and valor_clase:
            g.add((restriction, OWL.someValuesFrom, ns[sanitize_uri(valor_clase)]))
        elif tipo == "allValuesFrom" and valor_clase:
            g.add((restriction, OWL.allValuesFrom, ns[sanitize_uri(valor_clase)]))
        elif tipo == "minCardinality":
            try:
                g.add((restriction, OWL.minCardinality,
                       Literal(int(valor), datatype=XSD.nonNegativeInteger)))
            except (ValueError, TypeError):
                continue
        elif tipo == "maxCardinality":
            try:
                g.add((restriction, OWL.maxCardinality,
                       Literal(int(valor), datatype=XSD.nonNegativeInteger)))
            except (ValueError, TypeError):
                continue
        elif tipo == "exactCardinality":
            try:
                g.add((restriction, OWL.cardinality,
                       Literal(int(valor), datatype=XSD.nonNegativeInteger)))
            except (ValueError, TypeError):
                continue
        elif tipo == "hasValue":
            if valor_clase:
                g.add((restriction, OWL.hasValue, ns[sanitize_uri(valor_clase)]))
            else:
                g.add((restriction, OWL.hasValue, Literal(valor)))
        else:
            continue

        g.add((clase_uri, RDFS.subClassOf, restriction))

    # --- Reglas SWRL ---
    all_prop_names = set()
    for p in ontology.get("object_properties", []):
        all_prop_names.add(p["nombre"])
        inv = p.get("inversa")
        if inv and inv != "null":
            all_prop_names.add(inv)
    for p in ontology.get("datatype_properties", []):
        all_prop_names.add(p["nombre"])

    # 1) Reglas declaradas por el LLM (parser flexible)
    for regla in ontology.get("reglas_swrl", []):
        _add_swrl_rule(g, ns, regla, clases, all_prop_names)

    # 2) Reglas SWRL AUTO-GENERADAS desde propiedades inversas
    #    Para cada par (prop, inversa) creamos:
    #    prop(?x, ?y) -> inversa(?y, ?x)
    for prop in ontology.get("object_properties", []):
        prop_nombre = prop.get("nombre", "")
        inversa = prop.get("inversa")
        if not inversa or inversa == "null":
            continue

        regla_auto = {
            "nombre": f"auto_inv_{prop_nombre}",
            "descripcion": f"Inferencia automática: {prop_nombre} implica su inversa {inversa}",
            "antecedente": f"{prop_nombre}(?x, ?y)",
            "consecuente": f"{inversa}(?y, ?x)"
        }
        _add_swrl_rule(g, ns, regla_auto, clases, all_prop_names)

    # --- Instancias ---
    all_obj_prop_names = {p["nombre"] for p in ontology.get("object_properties", [])}
    for inv_name in inverse_map:
        all_obj_prop_names.add(inv_name)

    all_instances = {inst["nombre"] for inst in ontology.get("instancias_ejemplo", []) if inst.get("nombre")}

    for inst in ontology.get("instancias_ejemplo", []):
        nombre = inst.get("nombre", "")
        clase_raw = inst.get("clase", "")
        clase = _find_class_fuzzy(clase_raw, clases)
        if not nombre or not clase:
            continue

        inst_uri = ns[sanitize_uri(nombre)]
        g.add((inst_uri, RDF.type, ns[sanitize_uri(clase)]))
        g.add((inst_uri, RDF.type, OWL.NamedIndividual))

        for prop_name, prop_val in inst.get("propiedades", {}).items():
            prop_uri = ns[sanitize_uri(prop_name)]
            if prop_name in all_obj_prop_names and isinstance(prop_val, str):
                # Si el valor referencia otra instancia, usar URI; si no, literal
                if prop_val in all_instances or _find_class_fuzzy(prop_val, clases):
                    g.add((inst_uri, prop_uri, ns[sanitize_uri(prop_val)]))
                else:
                    g.add((inst_uri, prop_uri, Literal(prop_val)))
            else:
                g.add((inst_uri, prop_uri, Literal(prop_val)))

    return g


# ==========================================================
# REGLAS SWRL (formato compatible con Protégé SWRLTab)
# ==========================================================
def _clean_swrl_expression(expression):
    """Limpia la expresión SWRL eliminando sintaxis inválida del LLM."""
    # Eliminar comparaciones tipo "placa(?d) = ?f"
    expression = re.sub(r'\w+\([^)]+\)\s*=\s*\?\w+', '', expression)
    # Eliminar "some(?g; ...)"
    expression = re.sub(r'some\s*\([^)]*\)', '', expression)
    # Eliminar prefijos N3 tipo "a:" o "ont:" antes de nombres
    expression = re.sub(r'\b[a-z]+:', '', expression)
    # Eliminar "^" sueltos al principio/final o dobles
    expression = re.sub(r'\^\s*\^', '^', expression)
    expression = re.sub(r'^\s*\^\s*', '', expression)
    expression = re.sub(r'\s*\^\s*$', '', expression)
    return expression.strip()


def _convert_n3_to_swrl(expression):
    """Convierte sintaxis pseudo-Turtle '?x prop ?y' a formato SWRL 'prop(?x, ?y)'."""
    # Patrón: ?var1 prop ?var2  (con o sin "a:" prefix)
    # Lo convertimos a: prop(?var1, ?var2)
    pattern = r'(\?\w+)\s+(\w+)\s+(\?\w+)'

    def replace_n3(match):
        return f"{match.group(2)}({match.group(1)}, {match.group(3)})"

    converted = re.sub(pattern, replace_n3, expression)
    return converted


def _parse_swrl_atoms(expression, ns, clases, all_prop_names, shared_vars):
    """
    Parsea 'Clase(?x) ^ prop(?x, ?y)' en átomos RDF.
    shared_vars es un dict mutable que se comparte entre body y head
    para que la misma variable ?x sea el mismo URI en ambos.
    """
    expression = _clean_swrl_expression(expression)
    if not expression:
        return []

    # Convertir formato pseudo-Turtle del LLM a SWRL estándar
    expression = _convert_n3_to_swrl(expression)

    atoms = []
    parts = re.split(r'\s*\^\s*', expression)

    def get_var_uri(var_name):
        """Crea URI nombrada para la variable, reutilizando si ya existe."""
        clean = var_name.lstrip("?")
        if clean not in shared_vars:
            shared_vars[clean] = ns[f"var_{clean}"]
        return shared_vars[clean]

    for part in parts:
        part = part.strip()
        if not part:
            continue

        match = re.match(r'(\w+)\(([^)]+)\)', part)
        if not match:
            continue

        predicate = match.group(1)
        args_str = match.group(2)
        args = [a.strip() for a in args_str.split(",")]

        # Descartar átomos con más de 2 argumentos (SWRL no los soporta)
        if len(args) > 2:
            continue

        atom = BNode()

        # ¿Es un átomo de clase?
        clase_match = _find_class_fuzzy(predicate, clases)
        if clase_match and len(args) == 1 and args[0].startswith("?"):
            atoms.append((atom, SWRL.ClassAtom, {
                SWRL.classPredicate: ns[sanitize_uri(clase_match)],
                SWRL.argument1: get_var_uri(args[0]),
            }))
        # ¿Es un átomo de propiedad?
        elif predicate in all_prop_names and len(args) == 2:
            arg1 = get_var_uri(args[0]) if args[0].startswith("?") else ns[sanitize_uri(args[0])]
            arg2 = get_var_uri(args[1]) if args[1].startswith("?") else ns[sanitize_uri(args[1])]
            atoms.append((atom, SWRL.IndividualPropertyAtom, {
                SWRL.propertyPredicate: ns[sanitize_uri(predicate)],
                SWRL.argument1: arg1,
                SWRL.argument2: arg2,
            }))

    return atoms


def _build_swrl_atom_list(g, atoms):
    """Construye una lista RDF de átomos SWRL con tipo swrl:AtomList."""
    if not atoms:
        return RDF.nil

    # Primero escribir cada átomo
    for atom_node, atom_type, props in atoms:
        g.add((atom_node, RDF.type, atom_type))
        for pred, obj in props.items():
            g.add((atom_node, pred, obj))

    # Construir la lista enlazada con tipo swrl:AtomList
    head = BNode()
    current = head
    for i, (atom_node, _, _) in enumerate(atoms):
        g.add((current, RDF.type, SWRL.AtomList))
        g.add((current, RDF.first, atom_node))
        if i < len(atoms) - 1:
            next_node = BNode()
            g.add((current, RDF.rest, next_node))
            current = next_node
        else:
            g.add((current, RDF.rest, RDF.nil))

    return head


def _add_swrl_rule(g, ns, regla, clases, all_prop_names):
    """Añade una regla SWRL al grafo en formato compatible con Protégé."""
    nombre = regla.get("nombre", "")
    antecedente = regla.get("antecedente", "")
    consecuente = regla.get("consecuente", "")

    if not antecedente or not consecuente:
        return

    # Dict compartido: body y head usan las MISMAS URIs para las mismas variables
    shared_vars = {}

    ante_atoms = _parse_swrl_atoms(antecedente, ns, clases, all_prop_names, shared_vars)
    cons_atoms = _parse_swrl_atoms(consecuente, ns, clases, all_prop_names, shared_vars)

    if not ante_atoms or not cons_atoms:
        return

    # Declarar todas las variables como swrl:Variable con URI nombrada
    for var_name, var_uri in shared_vars.items():
        g.add((var_uri, RDF.type, SWRL.Variable))

    # Crear la regla
    rule_node = BNode()
    g.add((rule_node, RDF.type, SWRL.Imp))

    if nombre:
        g.add((rule_node, RDFS.label, Literal(nombre)))
    if regla.get("descripcion"):
        g.add((rule_node, RDFS.comment, Literal(regla["descripcion"])))

    ante_list = _build_swrl_atom_list(g, ante_atoms)
    cons_list = _build_swrl_atom_list(g, cons_atoms)

    g.add((rule_node, SWRL.body, ante_list))
    g.add((rule_node, SWRL.head, cons_list))


# ==========================================================
# GUARDAR ONTOLOGÍA
# ==========================================================
def save_ontology(graph, output_dir, filename_base):
    """Guarda la ontología en formato Turtle y RDF/XML."""
    os.makedirs(output_dir, exist_ok=True)

    ttl_path = os.path.join(output_dir, f"{filename_base}.ttl")
    graph.serialize(destination=ttl_path, format="turtle")

    rdf_path = os.path.join(output_dir, f"{filename_base}.owl")
    graph.serialize(destination=rdf_path, format="xml")

    return ttl_path, rdf_path


# ==========================================================
# VALIDACIÓN SPARQL
# ==========================================================
def validate_with_sparql(graph, sparql_query):
    """Ejecuta una consulta SPARQL contra el grafo."""
    try:
        results = graph.query(sparql_query)
        return list(results), None
    except Exception as e:
        return None, str(e)
