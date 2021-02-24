import logging
import requests
import re
import pyld.jsonld
import pyppeteer


# Media types
MEDIA_NQUADS = "application/n-quads"
MEDIA_JSONLD = "application/ld+json"
MEDIA_JSON = "applcation/json"
MEDIA_HTML = "text/html"
MEDIA_XML = "application/xml"

# Default base to use during expansion
DEFAULT_BASE = "https://example.net/"

# Common schema.org things
SO_ = "https://schema.org/"
SO_DATASET = f"{SO_}Dataset"
SO_IDENTIFIER = f"{SO_}identifier"
SO_VALUE = f"{SO_}value"
SO_URL = f"{SO_}url"

# regexp to match the typical location of the schema.org remote context
SO_MATCH = re.compile(r"http(s)?\://schema.org(/)?")

# Location of the schema.org context document
SO_CONTEXT_LOCATION = "https://raw.githubusercontent.com/schemaorg/schemaorg/main/data/releases/12.0/schemaorgcontext.jsonld"

# TODO: use a real cache
DOCUMENT_CACHE = {}


def cachingDocumentLoader(url, options={}):
    """
    Document loader for pyld.jsonld

    Used for operations like resolving remote context documents. This implementation provides
    a very simple cache (in memory dict) and overrides the location of the schema.org context
    to use the v12 version of the context document.
    """
    L = logging.getLogger("documentLoader")
    L.debug("DOC LOADER URL = %s", url)
    if SO_MATCH.match(url) is not None:
        L.debug("Forcing schema.org v12 context")
        url = SO_CONTEXT_LOCATION
    if url in DOCUMENT_CACHE:
        return DOCUMENT_CACHE[url]
    loader = pyld.jsonld.requests_document_loader()
    resp = loader(url, options=options)
    DOCUMENT_CACHE[url] = resp
    return resp


# Patch the new document loader into pyld
pyld.jsonld.set_document_loader(cachingDocumentLoader)
