import logging
import copy
import requests
import json
import pyld.jsonld
import cachecontrol
import flask
import asyncio
import pyppeteer

SO_NS = "https://schema.org/"
SO_HTTP_CONTEXT = {"@context": {"@vocab": "http://schema.org/"}}
SO_HTTPS_CONTEXT = {"@context": {"@vocab": "https://schema.org/"}}

# TODO: use a real cache
CONTEXT_CACHE = {}

REQUESTS_SESSION = cachecontrol.CacheControl(requests.session())

def cachingDocumentLoader(url, options={}):
    loader = pyld.jsonld.requests_document_loader()
    if url in CONTEXT_CACHE:
        return CONTEXT_CACHE[url]
    resp = loader(url, options=options)
    CONTEXT_CACHE[url] = resp
    return resp


pyld.jsonld.set_document_loader(cachingDocumentLoader)


def extractIdentifiers(jsonld: dict):
    """
    Extract PID, series_id, alt_identifiers from a block of JSON-LD

    Args:
        jsonld: normalized JSON ld document

    Returns:
        dict with pid, sid, and alternates

    """

    def _identifierValue(ident):
        if isinstance(ident, str):
            return ident
        if isinstance(ident, dict):
            v = ident.get("value", None)
            if v is None:
                v = ident.get("url", None)
            return v
        return str(ident)

    def _identifierValues(ident_list):
        res = []
        if ident_list is None:
            return res
        if isinstance(ident_list, str):
            return [_identifierValue(ident_list)]
        if isinstance(ident_list, dict):
            return [_identifierValue(ident_list)]
        for ident in ident_list:
            v = _identifierValue(ident)
            if not v is None:
                res.append(v)
        return res

    ids = []
    id_template = {
        "@id": None,  # Dataset.@id
        "url": None,  # Dataset.url
        "identifier": [],  # Values of any identifiers
    }
    for g in jsonld.get("@graph", []):
        g_type = g.get("@type", "")
        if g_type == SO_NS + "Dataset" or g_type == "Dataset":
            dsid = id_template.copy()
            dsid["@id"] = g.get("@id", None)
            dsid["url"] = g.get("url", None)
            identifiers = g.get(SO_NS + "identifier", None)
            if identifiers is None:
                identifiers = g.get("identifier", None)
            dsid["identifier"] = _identifierValues(identifiers)
            ids.append(dsid)
    return ids


class SoNormalize(object):
    def __init__(self):
        self.L = flask.current_app.logger
        self._processor = pyld.jsonld.JsonLdProcessor()

    def normalizeSchemaOrg(self, source):
        try:
            options = None
            expanded = self._processor.expand(source, options)

            ctx = copy.deepcopy(SO_HTTP_CONTEXT)
            opts = {"graph": True, "compactArrays": True}
            n1 = pyld.jsonld.compact(expanded, ctx, options=opts)
            n2 = copy.deepcopy(n1)
            n2["@context"]["@vocab"] = "https://schema.org/"
            ctxs = copy.deepcopy(n2["@context"])
            ctxs["https://schema.org/creator"] = {"@container": "@list"}
            ctxs["https://schema.org/identifier"] = {"@container": "@list"}
            opts["sorted"] = True
            n3 = pyld.jsonld.compact(n2, ctxs, options=opts)
            return n3, n2, n1, expanded
        except Exception as e:
            self.L.error("Normalize failed: %s", e)
            self.L.error("Cache: %s", CONTEXT_CACHE)
        return None, None, None, None


    def nquads(self, jsonld, base=None):
        options = {
            "format":"application/n-quads",
            "base": base
        }
        nq = pyld.jsonld.to_rdf(jsonld, options=options)
        return nq

async def downloadJsonRendered(url):
    _L = flask.current_app.logger
    _L.debug("Loading and rendering %s", url)
    # TODO: Should really be a single browser or pool of them rather than recreating
    # Actually, this is the preferred mode for doing this stuff:
    # 1. Only launch a browser when needed
    # 2. Get rid of it when done, fresh per request is better for longevity
    browser = await pyppeteer.launch(
        handleSIGINT=False,
        handleSIGTERM=False,
        handleSIGHUP=False
    )
    try:
        page = await browser.newPage()
        await page.goto(url)
        await page.waitForSelector('#Metadata')
        content = await page.content()
        _L.debug("JLD position: %s", content.find("ld+json"))
        jsonld = pyld.jsonld.load_html(
            content,
            url,
            profile=None,
            options={"extractAllScripts": True},
        )
    finally:
        await browser.close()
        _L.debug("Exit downloadJsonRendered")
    return jsonld


def downloadJson(url, headers={}):
    _L = flask.current_app.logger
    try:
        response = REQUESTS_SESSION.get(url, headers=headers, timeout=20)
    except requests.Timeout as e:
        _L.error("Reques to %s timed out", url)
        return {"ERROR": str(e)}, []
    _L.debug("Final URL = %s", response.url)
    try:
        jsonld = json.loads(response.content)
        return jsonld, response
    except Exception as e:
        _L.warning(e)
    jsonld = pyld.jsonld.load_html(
        response.content,
        response.url,
        profile=None,
        options={"extractAllScripts": True},
    )
    if len(jsonld) < 1:
        # try loading and rendering page
        jsonld = asyncio.run(downloadJsonRendered(url))
    return jsonld, response
