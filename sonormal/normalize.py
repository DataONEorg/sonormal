"""
Normalize JSON-LD and methods for normalized form operations.

"""

import logging
import requests
import json
import sonormal
import pyld.jsonld


def _getIdentifiers(doc):
    ids = []
    v = doc.get("@value", None)
    if not v is None:
        ids.append(v)
        return ids
    vs = doc.get(sonormal.SO_VALUE, [])
    for av in vs:
        v = av.get("@value", None)
        if v is not None:
            ids.append(v)
    return ids


def _getListIdentifiers(doc):
    ids = []
    for ident in doc.get("@list", []):
        ids += _getIdentifiers(ident)
    return ids


def _getDatasetIdentifiers(jdoc):
    ids = {"@id": [], "url": [], "identifier": []}
    t = jdoc.get("@type", [])
    if sonormal.SO_DATASET in t:
        _id = jdoc.get("@id", None)
        if _id is not None:
            ids["@id"].append(_id)
        _urls = jdoc.get(sonormal.SO_URL, [])
        for _url in _urls:
            u = _url.get("@id", None)
            if not u is None:
                ids["url"].append(u)
        for ident in jdoc.get(sonormal.SO_IDENTIFIER, []):
            ids["identifier"] += _getListIdentifiers(ident)
            ids["identifier"] += _getIdentifiers(ident)
    return ids


def getDatasetsIdentifiers(jdoc):
    """
    Extract PID, series_id, alt_identifiers from a list of JSON-LD blocks

    Args:
        jdoc: normalized JSON ld document

    Returns:
        dict with pid, sid, and alternates

    """
    ids = []
    for doc in jdoc:
        ids.append(_getDatasetIdentifiers(doc))
    return ids


def normalizeJsonld(jdoc, options={}):
    """
    Normalize a JSON-LD document structure.
    """
    opts = {"base": sonormal.DEFAULT_BASE}
    opts.update(options)
    rdfj = pyld.jsonld.to_rdf(jdoc, options=opts)
    return pyld.jsonld.from_rdf(rdfj)


def jsonldToNquads(jdoc, options={}):
    """
    Transform the JSON-LD document to n-quads format
    """
    opts = {"base": sonormal.DEFAULT_BASE}
    opts.update(options)
    return pyld.jsonld.to_rdf(jdoc, sonormal.MEDIA_NQUADS)
