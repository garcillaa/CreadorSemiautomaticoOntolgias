import os
from rdflib import Graph, Namespace, Literal, URIRef, BNode
from rdflib.namespace import RDF, RDFS, OWL, XSD


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


def sanitize_uri(name):
    """Convierte un nombre a un fragmento URI válido."""
    return name.replace(" ", "_").replace("á", "a").replace("é", "e").replace(
        "í", "i").replace("ó", "o").replace("ú", "u").replace("ñ", "n")


def ontology_to_owl(ontology, domain_name, base_uri=None):
    """Convierte la ontología JSON a un grafo RDF/OWL."""
    if not base_uri:
        safe_domain = sanitize_uri(domain_name.lower().replace(" ", "_"))
        base_uri = f"http://example.org/ontology/{safe_domain}#"

    g = Graph()
    ns = Namespace(base_uri)
    g.bind("ont", ns)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)
    g.bind("xsd", XSD)

    ont_uri = URIRef(base_uri.rstrip("#"))
    g.add((ont_uri, RDF.type, OWL.Ontology))
    g.add((ont_uri, RDFS.label, Literal(f"Ontología: {domain_name}")))

    clases = ontology.get("clases", {})
    for nombre_clase, info in clases.items():
        clase_uri = ns[sanitize_uri(nombre_clase)]
        g.add((clase_uri, RDF.type, OWL.Class))

        if isinstance(info, dict):
            if info.get("definicion"):
                g.add((clase_uri, RDFS.comment, Literal(info["definicion"])))
            superclase = info.get("superclase")
            if superclase and superclase != "null" and superclase in clases:
                g.add((clase_uri, RDFS.subClassOf, ns[sanitize_uri(superclase)]))
        elif isinstance(info, str):
            g.add((clase_uri, RDFS.comment, Literal(info)))

    for prop in ontology.get("object_properties", []):
        prop_uri = ns[sanitize_uri(prop["nombre"])]
        g.add((prop_uri, RDF.type, OWL.ObjectProperty))

        if prop.get("descripcion"):
            g.add((prop_uri, RDFS.comment, Literal(prop["descripcion"])))
        if prop.get("dominio") and prop["dominio"] in clases:
            g.add((prop_uri, RDFS.domain, ns[sanitize_uri(prop["dominio"])]))
        if prop.get("rango") and prop["rango"] in clases:
            g.add((prop_uri, RDFS.range, ns[sanitize_uri(prop["rango"])]))

    for prop in ontology.get("datatype_properties", []):
        prop_uri = ns[sanitize_uri(prop["nombre"])]
        g.add((prop_uri, RDF.type, OWL.DatatypeProperty))

        if prop.get("descripcion"):
            g.add((prop_uri, RDFS.comment, Literal(prop["descripcion"])))
        if prop.get("dominio") and prop["dominio"] in clases:
            g.add((prop_uri, RDFS.domain, ns[sanitize_uri(prop["dominio"])]))

        rango = prop.get("rango", "xsd:string")
        xsd_type = XSD_MAP.get(rango, XSD.string)
        g.add((prop_uri, RDFS.range, xsd_type))

    for rest in ontology.get("restricciones", []):
        clase_nombre = rest.get("clase", "")
        if clase_nombre not in clases:
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

        if tipo == "someValuesFrom" and valor in clases:
            g.add((restriction, OWL.someValuesFrom, ns[sanitize_uri(valor)]))
        elif tipo == "allValuesFrom" and valor in clases:
            g.add((restriction, OWL.allValuesFrom, ns[sanitize_uri(valor)]))
        elif tipo == "minCardinality":
            try:
                g.add((restriction, OWL.minCardinality, Literal(int(valor), datatype=XSD.nonNegativeInteger)))
            except (ValueError, TypeError):
                continue
        elif tipo == "maxCardinality":
            try:
                g.add((restriction, OWL.maxCardinality, Literal(int(valor), datatype=XSD.nonNegativeInteger)))
            except (ValueError, TypeError):
                continue
        elif tipo == "exactCardinality":
            try:
                g.add((restriction, OWL.cardinality, Literal(int(valor), datatype=XSD.nonNegativeInteger)))
            except (ValueError, TypeError):
                continue
        elif tipo == "hasValue":
            g.add((restriction, OWL.hasValue, Literal(valor)))
        else:
            continue

        g.add((clase_uri, RDFS.subClassOf, restriction))

    for inst in ontology.get("instancias_ejemplo", []):
        nombre = inst.get("nombre", "")
        clase = inst.get("clase", "")
        if not nombre or clase not in clases:
            continue

        inst_uri = ns[sanitize_uri(nombre)]
        g.add((inst_uri, RDF.type, ns[sanitize_uri(clase)]))
        g.add((inst_uri, RDF.type, OWL.NamedIndividual))

        for prop_name, prop_val in inst.get("propiedades", {}).items():
            prop_uri = ns[sanitize_uri(prop_name)]
            if isinstance(prop_val, str) and prop_val in clases:
                g.add((inst_uri, prop_uri, ns[sanitize_uri(prop_val)]))
            else:
                g.add((inst_uri, prop_uri, Literal(prop_val)))

    return g


def save_ontology(graph, output_dir, filename_base):
    """Guarda la ontología en formato Turtle y RDF/XML."""
    os.makedirs(output_dir, exist_ok=True)

    ttl_path = os.path.join(output_dir, f"{filename_base}.ttl")
    graph.serialize(destination=ttl_path, format="turtle")

    rdf_path = os.path.join(output_dir, f"{filename_base}.owl")
    graph.serialize(destination=rdf_path, format="xml")

    return ttl_path, rdf_path


def validate_with_sparql(graph, sparql_query):
    """Ejecuta una consulta SPARQL contra el grafo y devuelve los resultados."""
    try:
        results = graph.query(sparql_query)
        return list(results), None
    except Exception as e:
        return None, str(e)
