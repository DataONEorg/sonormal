import logging
import copy
import requests
import json
import pyld.jsonld
import cachecontrol

SO_HTTP_CONTEXT = {"@context": {"@vocab": "http://schema.org/"}}
SO_HTTPS_CONTEXT = {"@context": {"@vocab": "https://schema.org/"}}

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


class SoNormalize(object):
    def __init__(self):
        self.L = logging.getLogger(self.__class__.__name__)
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
            return n3
        except Exception as e:
            self.L.error("Normalize failed: %s", e)
            self.L.error("Cache: %s", CONTEXT_CACHE)
        return None


def downloadJson(url, headers={}):
    _L = logging.getLogger("downloadJson")
    response = REQUESTS_SESSION.get(url, headers=headers)
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
    return jsonld, response
    #normalizer = SoNormalize()
    #return normalizer.normalizeSchemaOrg(jsonld)
