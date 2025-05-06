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

__L = logging.getLogger("sonormal")

def _getValueOrURI(doc):
    v = doc.get("@value", None)
    if not v is None:
        __L.debug(f"_getValueOrURI got @value: {v}")
        # Check if the value is a URI
        if isinstance(v, str) and v.startswith(("http", "https", "doi:", "urn:")):
            __L.debug(f"_getValueOrURI found valid @value URI: {v}")
            return v
        __L.debug(f"_getValueOrURI not a URI: {v}")
    __L.debug(f"_getValueOrURI found: {doc.get('@id', None)}")
    return doc.get("@id", None)


def _getURLs(doc):
    urls = []
    us = doc.get(sonormal.SO_URL, [])
    for au in us:
        u = au.get("@id", None)
        if u is not None:
            urls.append(u)
    __L.debug(f"_getURLs got urls: {urls}")
    return urls


def _getListURLs(doc):
    urls = []
    for url in doc.get("@list", []):
        urls += _getURLs(url)
    return urls


def _getIdentifiers(doc):
    ids = []
    v = doc.get("@value", None)
    if not v is None:
        __L.debug(f"_getIdentifiers got @value: {v}")
        ids.append(v)
        __L.debug(f"_getIdentifiers ids: {ids}")
    vs = doc.get(sonormal.SO_VALUE, [])
    __L.debug(f"_getIdentifiers got SO:value: {vs}")
    for av in vs:
        v = av.get("@value", None)
        if not v is None:
            ids.append(v)
    __L.debug(f"_getIdentifiers ids: {ids}")
    return ids


def _getListIdentifiers(doc):
    ids = []
    for ident in doc.get("@list", []):
        ids += _getIdentifiers(ident)
    return ids


def _getDatasetIdentifiers(jdoc):
    t = jdoc.get("@type", [])
    if not sonormal.SO_DATASET in t:
        return None
    ids = {"@id": [], "url": [], "identifier": []}
    _id = jdoc.get("@id", None)
    if _id is not None:
        ids["@id"].append(_id)
    _urls = jdoc.get(sonormal.SO_URL, [])
    for _url in _urls:
        u = _getValueOrURI(_url)
        if not u is None:
            ids["url"].append(u)
    for ident in jdoc.get(sonormal.SO_IDENTIFIER, []):
        _identstr = json.dumps(ident, indent=2)
        __L.debug(level=5, msg=f'Found entry under {sonormal.SO_IDENTIFIER}:\n{_identstr}')
        ids["identifier"] += _getListIdentifiers(ident)
        ids["identifier"] += _getIdentifiers(ident)
        ids["url"] += _getListURLs(ident)
        ids["url"] += _getURLs(ident)
        u = _getValueOrURI(ident)
        if not u is None:
            ids["identifier"].append(u)
    __L.debug(f"_getDatasetIdentifiers ids: {ids}")
    return ids


def getDatasetsIdentifiers(jdoc):
    """
    Extract PID, series_id, alt_identifiers from a list of JSON-LD blocks

    Args:
        jdoc: framed with Dataset aspect

    Returns:
        dict with pid, sid, and alternates

    """
    ids = []
    for doc in jdoc:
        __L.log(level=5, msg=f"getDatasetsIdentifiers doc: {doc}")
        _ids = _getDatasetIdentifiers(doc)
        if not _ids is None:
            ids.append(_ids)
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


def frameSODataset(jdoc, frame_doc=None, options={}):
    __L.debug("Framing")
    if frame_doc is None:
        frame_doc = copy.deepcopy(sonormal.SO_DATASET_FRAME)
    try:
        fdoc = pyld.jsonld.frame(jdoc, frame_doc, options=options)
        __L.info("fdoc OK")
        return pyld.jsonld.expand(fdoc, options=options)
    except Exception as e:
        __L.error(e)
    __L.info("fdoc FAIL")
    return []


def compactSODataset(jdoc, options={}, context=None):
    opts = {"base": sonormal.DEFAULT_BASE}
    opts.update(options)
    if context is None:
        context = copy.deepcopy(sonormal.SO_COMPACT_CONTEXT)
        #Assume @base was set in the context, if provided
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
