import os
import logging
import requests
import re
import string
import json
import pyld.jsonld
import urllib.parse as urllib_parse
import diskcache
import atexit
import copy

__L = logging.getLogger("sonormal")

# Media types
MEDIA_NQUADS = "application/n-quads"
MEDIA_JSONLD = "application/ld+json"
MEDIA_JSON = "application/json"
MEDIA_HTML = "text/html"
MEDIA_XHTML = "application/xml+xhtml"
MEDIA_XML = "application/xml"

# Default base to use during expansion
DEFAULT_BASE = "https://example.net/"

# Context cache folder
CONTEXT_CACHE = os.path.expanduser("~/.local/var/sonormal/contexts")
os.makedirs(CONTEXT_CACHE, exist_ok=True)

# Location of the schema,.org context
SCHEMA_ORG_CONTEXT_SOURCE = "https://schema.org/docs/jsonldcontext.jsonld"

SCHEMA_ORG_HTTP_CONTEXT_FILE = "schema_org_http_context.jsonld"
SCHEMA_ORG_HTTPS_CONTEXT_FILE = "schema_org_https_context.jsonld"
SCHEMA_ORG_HTTP_LIST_CONTEXT_FILE = "schema_org_http_list_context.jsonld"

SCHEMA_ORG_CONTEXT_URLS = [
    "http://schema.org",
    "http://schema.org/",
    "https://schema.org",
    "https://schema.org/",
    "http://schema.org/docs/jsonldcontext.jsonld",
    "https://schema.org/docs/jsonldcontext.jsonld",
]
SO_CONTEXT = {}
SOS_CONTEXT = {}
SOL_CONTEXT = {}


# Common schema.org things
SO_ = "https://schema.org/"
SO_DATASET = f"{SO_}Dataset"
SO_IDENTIFIER = f"{SO_}identifier"
SO_VALUE = f"{SO_}value"
SO_URL = f"{SO_}url"
SO_PROPERTY_ID = f"{SO_}propertyID"

SO_COMPACT_CONTEXT = {"@context": ["https://schema.org/", {"id": "id", "type": "type"}]}

SO_DATASET_FRAME = {
    "@context": {"@vocab": "https://schema.org/"},
    "@type": "Dataset",
    "identifier": {},
    "creator": {},
}

# regexp to match the typical location of the schema.org remote context
SO_MATCH = re.compile(r"http(s)?\://schema.org(/)?")

# Location of the schema.org context document
# Currently forcing to a specific revision of SO that uses the https context
# More detail at https://github.com/schemaorg/schemaorg/pull/2814#issuecomment-795667992
# SO_CONTEXT_LOCATION = "https://schema.org/docs/jsonldcontext.jsonld"
# Set to use a specific version of schema.org context
SO_CONTEXT_LOCATION = "https://raw.githubusercontent.com/schemaorg/schemaorg/836cae785cfcb09fe69d0a611be9b8c73b67a0d4/data/releases/12.0/schemaorgcontext.jsonld"
FORCE_SO_VERSION = True

# Timeout for the document loader requests
REQUEST_TIMEOUT = 30  # seconds

# Default content type when not provided in server response
# pyld defaults to application/octet-stream, which makes sense
# but means sloppy HTML responses are not handled i4n load_document()
DEFAULT_RESPONSE_CONTENT_TYPE = MEDIA_HTML

# Content negotiation support is pretty bad. This *should* work, but will
# not be respected on some services. It's generally OK to fall back to
# application/ld+json or text/html or even */*, though should be applied
# consistently per target.
DEFAULT_REQUEST_ACCEPT_HEADERS = f"{MEDIA_JSONLD};q=1.0, {MEDIA_JSON};q=0.9, {MEDIA_HTML};q=0.8, {MEDIA_XHTML};q=0.7, */*;q=0.1"

# Path to the document cache
DOCUMENT_CACHE_PATH = os.path.expanduser("~/.local/share/sonormal/cache")
os.makedirs(DOCUMENT_CACHE_PATH, exist_ok=True)

DOCUMENT_CACHE_TIMEOUT = 300  # Cache object expiration in seconds

# Global cache for downloaded stuff, especially context documents
DOCUMENT_CACHE = diskcache.Cache(DOCUMENT_CACHE_PATH)


def __cleanup():
    global DOCUMENT_CACHE
    DOCUMENT_CACHE.close()


atexit.register(__cleanup)


def prepareSchemaOrgLocalContexts(
    context_folder=CONTEXT_CACHE, src_url=SCHEMA_ORG_CONTEXT_SOURCE, exist_ok=False
):
    """
    Download a copy of the schema.org context and create variants.

    The variants include a copy that uses https://schema.org/ namespace
    and a copy that uses http://schema.org/ namespace and adds the
    @list container type to `creator` and `identifier` to preserve order.

    These variants are used in the namespace normalization process and
    to facilitate ordered extraction of identifier and creator values
    such as from Dataset structures.

    Args:
        src_url (string): URL of the document to retrieve
        exist_ok (bool): If True, then OK to overwrite existing

    Returns:
        dict: map of paths to context files

    Raises:
        ValueError if docs can't be overwritten or context can't be downloaded
    """
    global SO_CONTEXT
    global SOS_CONTEXT
    global SOL_CONTEXT

    paths = {
        "so": os.path.join(context_folder, SCHEMA_ORG_HTTP_CONTEXT_FILE),
        "sos": os.path.join(context_folder, SCHEMA_ORG_HTTPS_CONTEXT_FILE),
        "sol": os.path.join(context_folder, SCHEMA_ORG_HTTP_LIST_CONTEXT_FILE),
    }
    __L.debug("PATHS = %s", paths)
    if (
        os.path.exists(paths["so"])
        and os.path.exists(paths["sos"])
        and os.path.exists(paths["sol"])
        and not exist_ok
    ):
        raise ValueError(
            f"Schema.org context documents already present in {context_folder}"
        )
    headers = {"Accept": f"{MEDIA_JSONLD};q=1.0, {MEDIA_JSON};q=0.9"}
    response = requests.get(src_url, headers=headers, timeout=10, allow_redirects=True)
    if not response.status_code == requests.codes.OK:
        raise ValueError(f"Unable to retrieve schema.org context from {src_url}")
    so_context = response.json()
    with open(paths["so"], "w") as so_dest:
        json.dump(so_context, so_dest, indent=2)
    # Create context doc with https://schema.org/
    sos_context = copy.deepcopy(so_context)
    sos_context["@context"]["@vocab"] = "https://schema.org/"
    sos_context["@context"]["schema"] = "https://schema.org/"
    with open(paths["sos"], "w") as so_dest:
        json.dump(sos_context, so_dest, indent=2)

    # Add @list to identifier and creator
    so_context["@context"]["creator"] = {"@id": "schema:creator", "@container": "@list"}
    so_context["@context"]["identifier"] = {
        "@id": "schema:identifier",
        "@container": "@list",
    }
    with open(paths["sol"], "w") as so_dest:
        json.dump(so_context, so_dest, indent=2)
    for url in SCHEMA_ORG_CONTEXT_URLS:
        SO_CONTEXT[url] = paths["so"]
        SOS_CONTEXT[url] = paths["sos"]
        SOL_CONTEXT[url] = paths["sol"]
    return paths


def localRequestsDocumentLoader(context_map={}):
    """Return a pyld.jsonld document loader.

    The document loader intercepts requests to retrieve a remote context
    and replaces with a local copy of the document.

    Args:
        context_map (dict): map of context URL to local document

    Returns:
        dict:
    """

    def localRequestsDocumentLoaderImpl(url, options={}):
        _url = url.lower().strip()
        doc = context_map.get(_url, None)
        if not doc is None:
            res = {
                "contextUrl": None,
                "documentUrl": "https://schema.org/docs/jsonldcontext.jsonld",
                "contentType": "application/ld+json",
                "document": json.load(open(doc, "r")),
            }
            return res
        # No mapping available, fall back to using the requests loader
        loader = pyld.jsonld.requests_document_loader()
        return loader(url)

    return localRequestsDocumentLoaderImpl


def isHttpsSchemaOrg(exp_doc) -> bool:
    """True if exp_doc is using https://schema.org/ namespace

    Returns the first match of the use of https://schema.org or
    http://schema.org on a key found by recursing through the
    object.

    Args:
        exp_doc: expanded JSON-LD document

    Returns:
        bool: True is document is using `https://schema.org` namespace
    """
    for i, v in enumerate(exp_doc):
        if isinstance(v, dict):
            return isHttpsSchemaOrg(exp_doc[i])
        if isinstance(v, str):
            if v.startswith("https://schema.org"):
                return True
            elif v.startswith("http://schema.org"):
                return False
    return False


def switchToHttpSchemaOrg(doc):
    """Convert SO JSONLD namespace from https://schema.org/ to http://schema.org/

    The document is expanded and compacted with only schema.org properties
    compacted. Properties in other namespaces remain expanded.

    Args:
        doc: schema.org JSON-LD document

    Returns:
        document: JSON-LD document using http://schema.org/ namespace
    """
    # First expand the document
    expanded = pyld.jsonld.expand(doc)

    # Determine which context to apply
    is_https = isHttpsSchemaOrg(expanded)
    context_map = SO_CONTEXT
    if is_https:
        context_map = SOS_CONTEXT
    options = {
        "documentLoader": localRequestsDocumentLoader(context_map=context_map),
    }

    # Compact the schema.org elements of the document
    context = {"@context": "https://schema.org/"}
    return pyld.jsonld.compact(expanded, context, options)


def addSchemaOrgListContainer(doc):
    """Expand document with context including @list container for creator and identifier

    Args:
        doc: Schema.org document using http://schema.org/ namespace

    Returns:
        document: Expanded JSON-LD
    """
    options = {
        "documentLoader": localRequestsDocumentLoader(context_map=SOL_CONTEXT),
    }
    expanded = pyld.jsonld.expand(doc, options)
    return expanded


class ObjDict(dict):
    def __getattr__(self, name):
        if name in self:
            return self[name]
        else:
            raise AttributeError("No such attribute: " + name)

    def __setattr__(self, name, value):
        self[name] = value

    def __delattr__(self, name):
        if name in self:
            del self[name]
        else:
            raise AttributeError("No such attribute: " + name)


class RequestsSessionTrack(requests.Session):
    def get_redirect_target(self, resp):
        L = logging.getLogger("sonormal")
        L.debug("Response [%s] from %s", resp.status_code, resp.request.url)
        loc = super().get_redirect_target(resp)
        if not loc is None:
            L.info("Redirect target: %s %s", resp.status_code, loc)
        return loc


def requests_document_loader_history(secure=False, **kwargs):
    """
    Create a Requests document loader.

    This implementation differs from the original:
    * The response history is returned
    * Link responses are examined for alternate locations
    * A profile if provided is compared with link profiles during comparison

    Can be used to setup extra Requests args such as verify, cert, timeout,
    or others.
    :param secure: require all requests to use HTTPS (default: False).
    :param **kwargs: extra keyword args for Requests get() call.
    :return: the RemoteDocument loader function.
    """

    def loader(url, options={}):
        """
        Retrieves JSON-LD at the given URL.
        :param url: the URL to retrieve.
        :return: the RemoteDocument.
        """
        __L.debug("ENTER: loader")
        _sess = RequestsSessionTrack()
        try:
            # validate URL
            pieces = urllib_parse.urlparse(url)
            if (
                not all([pieces.scheme, pieces.netloc])
                or pieces.scheme not in ["http", "https"]
                or set(pieces.netloc)
                > set(string.ascii_letters + string.digits + "-.:")
            ):
                raise pyld.jsonld.JsonLdError(
                    'URL could not be dereferenced; only "http" and "https" '
                    "URLs are supported.",
                    "jsonld.InvalidUrl",
                    {"url": url},
                    code="loading document failed",
                )
            if secure and pieces.scheme != "https":
                raise pyld.jsonld.JsonLdError(
                    "URL could not be dereferenced; secure mode enabled and "
                    'the URL\'s scheme is not "https".',
                    "jsonld.InvalidUrl",
                    {"url": url},
                    code="loading document failed",
                )
            headers = options.get("headers")
            if headers is None:
                headers = {"Accept": DEFAULT_REQUEST_ACCEPT_HEADERS}

            __L.debug("HEADER = %s", headers)
            response = _sess.get(url, headers=headers, **kwargs)

            content_type = response.headers.get("content-type")
            if not content_type:
                content_type = DEFAULT_RESPONSE_CONTENT_TYPE
            doc = {
                "contentType": content_type,
                "contextUrl": None,
                "documentUrl": response.url,
                "document": None,  # document is parsed later
                "response": None,  # Include the response for history/performance review
            }
            link_header = response.headers.get("link")
            if link_header:
                linked_context = pyld.jsonld.parse_link_header(link_header).get(
                    pyld.jsonld.LINK_HEADER_REL
                )
                # only 1 related link header permitted when matching for context
                if linked_context and content_type != "application/ld+json":
                    if isinstance(linked_context, list):
                        raise pyld.jsonld.JsonLdError(
                            "URL could not be dereferenced, "
                            "it has more than one "
                            "associated HTTP Link Header.",
                            "jsonld.LoadDocumentError",
                            {"url": url},
                            code="multiple context link headers",
                        )
                    doc["contextUrl"] = linked_context["target"]
                linked_alternate = pyld.jsonld.parse_link_header(link_header).get(
                    "alternate"
                )
                # Linked alternate may be a list....
                # A. type == application/ld+json, no profile
                # OR
                # B. type == application/ld+json, profile == supplied profile
                # if not JSON-LD, alternate may point there
                the_linked_alternate = None
                if linked_alternate:
                    _profile = options.get("profile", None)
                    if isinstance(linked_alternate, list):
                        for candidate in linked_alternate:
                            __L.debug("CANDIDATE Link: %s", candidate)
                            if candidate.get("type") == "application/ld+json":
                                if _profile is not None:
                                    if candidate.get("profile") == _profile:
                                        the_linked_alternate = candidate
                                        break
                                else:
                                    the_linked_alternate = candidate
                                    break
                    else:
                        the_linked_alternate = linked_alternate
                if (
                    the_linked_alternate
                    and the_linked_alternate.get("type") == "application/ld+json"
                    and not re.match(r"^application\/(\w*\+)?json$", content_type)
                ):
                    doc["contentType"] = "application/ld+json"
                    doc["documentUrl"] = pyld.jsonld.prepend_base(
                        url, the_linked_alternate["target"]
                    )
                    # recurse into loader with the new URL
                    return loader(doc["documentUrl"], options=options)
            # parse the json response and return
            # Do not parse JSON here. It needs to be done in load_document to handle the
            # situation where JSON-LD needs to be extracted from a HTML response.
            # doc['document'] = response.json()
            doc["document"] = response.content.decode()
            doc["response"] = response
            return doc
        except pyld.jsonld.JsonLdError as e:
            raise e
        except Exception as cause:
            raise pyld.jsonld.JsonLdError(
                "Could not retrieve a JSON-LD document from the URL.",
                "jsonld.LoadDocumentError",
                code="loading document failed",
                cause=cause,
            )

    return loader


def cachingDocumentLoader(url, options={}):
    """
    Document loader for pyld.jsonld

    Used for operations like resolving remote context documents. This implementation provides
    a very simple cache (in memory dict) and overrides the location of the schema.org context
    to use the v12 version of the context document.

    Install by calling:

      pyld.jsonld.set_document_loader(sonormal.cachingDocumentLoader)
    """
    __L.debug("DOC LOADER URL = %s", url)
    if FORCE_SO_VERSION and SO_MATCH.match(url) is not None:
        __L.debug("Forcing schema.org v12 context")
        url = SO_CONTEXT_LOCATION
    global DOCUMENT_CACHE
    if url in DOCUMENT_CACHE:
        __L.debug("From cache")
        return DOCUMENT_CACHE[url]
    options.setdefault("timeout", REQUEST_TIMEOUT)
    options.setdefault("allow_redirects", True)
    loader = requests_document_loader_history(
        timeout=options.get("timeout"), allow_redirects=options.get("allow_redirects")
    )
    resp = loader(url, options=options)
    # loader raises on error, so failed requests are not cached
    DOCUMENT_CACHE.set(url, resp, expire=DOCUMENT_CACHE_TIMEOUT)
    return resp


def installDocumentLoader(expire_existing=False):
    __L.info("Installing cachingDocumentLoader")
    __L.info("FORCE_SO_VERSION: %s", FORCE_SO_VERSION)
    pyld.jsonld.set_document_loader(cachingDocumentLoader)
    global DOCUMENT_CACHE
    if expire_existing:
        DOCUMENT_CACHE.expire()
