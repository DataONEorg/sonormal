"""
Normalize JSON-LD and methods for normalized form operations.

"""

import logging
import copy
import requests
import json
import sonormal
import pyld.jsonld
import c14n


def _getValueOrURI(doc):
    v = doc.get("@value", None)
    if v is not None:
        return v
    return doc.get("@id", None)


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
            u = _getValueOrURI(_url)
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


def _forceSODatasetLists(jdoc):
    _forced = ["creator", "identifier"]
    modified = copy.deepcopy(jdoc)
    ctx = modified.get("@context", None)
    if isinstance(ctx, list):
        for _f in _forced:
            ctx.append({_f:{"@container":"@list"}})
        #ctx.append({"creator": {"@container": "@list"}})
        modified["@context"] = ctx
        return modified
    if isinstance(ctx, str):
        ctx = [ctx, ]
        for _f in _forced:
            ctx.append({_f:{"@container":"@list"}})

        modified["@context"] = ctx
        return modified
    if isinstance(ctx, dict):
        for k in _forced:
            ctx[k] = {"@container": "@list"}
        modified["@context"] = ctx
    return modified


def forceSODatasetLists(jdoc):
    if isinstance(jdoc, dict):
        return _forceSODatasetLists(jdoc)
    docs = []
    for doc in jdoc:
        docs.append(_forceSODatasetLists(doc))
    return docs


def frameSODataset(jdoc):
    frame_doc = copy.deepcopy(sonormal.SO_DATASET_FRAME)
    fdoc = pyld.jsonld.frame(jdoc, frame_doc)
    return pyld.jsonld.expand(fdoc)


def compactSODataset(jdoc, options={}):
    opts = {"base": sonormal.DEFAULT_BASE}
    opts.update(options)
    context = copy.deepcopy(sonormal.SO_COMPACT_CONTEXT)
    if options.get("base", None) is not None:
        context["@context"].append({"@base":options["base"]})
    return pyld.jsonld.compact(jdoc, context, options=opts)


def normalizeJsonld(jdoc, options={}):
    """
    Normalize a JSON-LD document structure.
    """
    opts = {
        "algorithm": "URDNA2015",
        "base": sonormal.DEFAULT_BASE,
        "format": sonormal.MEDIA_NQUADS,
    }
    opts.update(options)
    _rdf = pyld.jsonld.normalize(jdoc, options=opts)
    return pyld.jsonld.from_rdf(_rdf, options=opts)


def jsonldToNquads(jdoc, options={}):
    """
    Transform the JSON-LD document to n-quads format
    """
    opts = {
        "algorithm": "URDNA2015",
        "base": sonormal.DEFAULT_BASE,
        "format": sonormal.MEDIA_NQUADS,
    }
    opts.update(options)
    return pyld.jsonld.normalize(jdoc, options=opts)


def canonicalizeJson(jdoc):
    b = c14n.canonicalize(jdoc)
    return b.decode()
