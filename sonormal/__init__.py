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
from sonormal.config import settings

__L = logging.getLogger("sonormal")

# Media types
MEDIA_NQUADS = "application/n-quads"
MEDIA_JSONLD = "application/ld+json"
MEDIA_JSON = "application/json"
MEDIA_HTML = "text/html"
MEDIA_XHTML = "application/xml+xhtml"
MEDIA_XML = "application/xml"

# Default base to use during expansion
DEFAULT_BASE = settings.get("DEFAULT_BASE", "https://example.net/")

# Context cache folder
DEFAULT_CONTEXT_CACHE = settings.get(
    "DEFAULT_CONTEXT_CACHE", os.path.expanduser("~/.local/var/sonormal/contexts")
)
os.makedirs(DEFAULT_CONTEXT_CACHE, exist_ok=True)

# Location of the schema,.org context
SCHEMA_ORG_CONTEXT_SOURCE = settings.get(
    "SCHEMA_ORG_CONTEXT_SOURCE", "https://schema.org/docs/jsonldcontext.jsonld"
)

SCHEMA_ORG_HTTP_CONTEXT_FILE = settings.get(
    "SCHEMA_ORG_HTTP_CONTEXT_FILE", "schema_org_http_context.jsonld"
)
SCHEMA_ORG_HTTPS_CONTEXT_FILE = settings.get(
    "SCHEMA_ORG_HTTPS_CONTEXT_FILE", "schema_org_https_context.jsonld"
)
SCHEMA_ORG_HTTP_LIST_CONTEXT_FILE = settings.get(
    "SCHEMA_ORG_HTTP_LIST_CONTEXT_FILE", "schema_org_http_list_context.jsonld"
)

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
SO_CONTEXTS_PREPARED = False

# Common schema.org things
SO_ = "http://schema.org/"
SO_DATASET = f"{SO_}Dataset"
SO_IDENTIFIER = f"{SO_}identifier"
SO_VALUE = f"{SO_}value"
SO_URL = f"{SO_}url"
SO_PROPERTY_ID = f"{SO_}propertyID"

SO_COMPACT_CONTEXT = {"@context": ["http://schema.org/", {"id": "id", "type": "type"}]}

SO_DATASET_FRAME = {
    "@context": "http://schema.org/",
    "@type": "Dataset",
    "identifier": {},
    "creator": {}
}

# regexp to match the typical location of the schema.org remote context
SO_MATCH = re.compile(r"http(s)?\://schema.org(/)?")

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
DEFAULT_REQUEST_ACCEPT_HEADERS = f"{MEDIA_JSONLD};q=1.0, {MEDIA_JSON};q=0.9, {MEDIA_HTML};q=0.8, {MEDIA_XHTML};q=0.7"

# Path to the document cache
DOCUMENT_CACHE_PATH = settings.get(
    "DOCUMENT_CACHE_PATH", os.path.expanduser("~/.local/share/sonormal/cache")
)
os.makedirs(DOCUMENT_CACHE_PATH, exist_ok=True)

DOCUMENT_CACHE_TIMEOUT = 300  # Cache object expiration in seconds

# Global cache for downloaded stuff, especially context documents
DOCUMENT_CACHE = diskcache.Cache(DOCUMENT_CACHE_PATH)


def __cleanup():
    global DOCUMENT_CACHE
    DOCUMENT_CACHE.close()


atexit.register(__cleanup)


def prepareSchemaOrgLocalContexts(
    context_folder=DEFAULT_CONTEXT_CACHE,
    src_url=SCHEMA_ORG_CONTEXT_SOURCE,
    refresh=False,
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
    global SO_CONTEXTS_PREPARED

    paths = {
        "so": os.path.join(context_folder, SCHEMA_ORG_HTTP_CONTEXT_FILE),
        "sos": os.path.join(context_folder, SCHEMA_ORG_HTTPS_CONTEXT_FILE),
        "sol": os.path.join(context_folder, SCHEMA_ORG_HTTP_LIST_CONTEXT_FILE),
    }
    for url in SCHEMA_ORG_CONTEXT_URLS:
        SO_CONTEXT[url] = paths["so"]
        SOS_CONTEXT[url] = paths["sos"]
        SOL_CONTEXT[url] = paths["sol"]
    if (
        os.path.exists(paths["so"])
        and os.path.exists(paths["sos"])
        and os.path.exists(paths["sol"])
        and not refresh
    ):
        # Contexts already available
        SO_CONTEXTS_PREPARED = True
        __L.debug("Local contexts already exist")
        return paths

    __L.info("Downloading and preparing SO contexts")
    # Download context files
    headers = {"Accept": f"{MEDIA_JSONLD};q=1.0, {MEDIA_JSON};q=0.9"}
    response = requests.get(src_url, headers=headers, timeout=10, allow_redirects=True)
    if not response.status_code == requests.codes.OK:
        raise ValueError(f"Unable to retrieve schema.org context from {src_url}")
    so_context = response.json()
    #SO overrides @id and @type. Don't do that...
    so_context["@context"]["id"] = "id"
    so_context["@context"]["type"] = "type"
    with open(paths["so"], "w") as so_dest:
        json.dump(so_context, so_dest, indent=2)
    # Create context doc with https://schema.org/
    sos_context = copy.deepcopy(so_context)
    sos_context["@context"]["@vocab"] = "https://schema.org/"
    sos_context["@context"]["schema"] = "https://schema.org/"
    with open(paths["sos"], "w") as so_dest:
        json.dump(sos_context, so_dest, indent=2)

    # Add @list to identifier, creator, and description
    so_context["@context"]["creator"] = {"@id": "schema:creator", "@container": "@list"}
    so_context["@context"]["identifier"] = {
        "@id": "schema:identifier",
        "@container": "@list",
    }
    so_context["@context"]["description"] = {
        "@id": "schema:description",
        "@container": "@list",
    }
    with open(paths["sol"], "w") as so_dest:
        json.dump(so_context, so_dest, indent=2)
    SO_CONTEXTS_PREPARED = True
    return paths


class ObjDict(dict):
    """
    Implements a dict that enables access to properties like an object.
    """

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
        loc = super().get_redirect_target(resp)
        L.debug("Redirect target: %s %s", resp.status_code, str(loc))
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
        __L.debug("Enter loader")
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

            __L.debug("Request headers: %s", headers)
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
                    __L.debug("Linked alternate: %s", the_linked_alternate["target"])
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
            doc["document"] = response.text
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


def localRequestsDocumentLoader(
    context_map={}, document_cache=None, fallback_loader=None
):
    """Return a pyld.jsonld document loader.

    The document loader intercepts requests to retrieve a remote context
    and replaces with a local copy of the document.

    Args:
        context_map (dict): map of context URL to local document
        document_cache (dict like): cache for documents, can be dict or DiskCache
        fallback_loader: loader to use if not local or in cache

    Returns:
        dict:
    """

    def localRequestsDocumentLoaderImpl(url, options={}):
        # is a cached copy available?
        if not document_cache is None:
            if url in document_cache:
                __L.debug("Cache hit: %s", url)
                return document_cache[url]
        # does URL match something in the context_map?
        doc = context_map.get(url, None)
        if not doc is None:
            res = {
                "contextUrl": None,
                "documentUrl": "https://schema.org/docs/jsonldcontext.jsonld",
                "contentType": "application/ld+json",
                "document": json.load(open(doc, "r")),
            }
            return res
        # No mapping available, fall back to using the fallback_loader
        res = fallback_loader(url, options)
        if not document_cache is None:
            # cache the response for later reuse
            if isinstance(document_cache, dict):
                document_cache[url] = res
            else:
                try:
                    document_cache.set(url, res, expire=DOCUMENT_CACHE_TIMEOUT)
                except Exception as e:
                    __L.warning("Unable to cache response from %s", url)
        return res

    # if no fallback is provided, create a default one using the pyld requests loader
    if fallback_loader is None:
        fallback_loader = pyld.jsonld.requests_document_loader()
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


def switchToHttpSchemaOrg(doc, options={}):
    """Convert SO JSONLD namespace from https://schema.org/ to http://schema.org/

    The document is expanded and compacted with only schema.org properties
    compacted. Properties in other namespaces remain expanded.

    Args:
        doc: schema.org JSON-LD document

    Returns:
        document: JSON-LD document using http://schema.org/ namespace
    """
    # First expand the document
    # options may include a default base for the document
    opts = {
        "documentLoader": localRequestsDocumentLoader(context_map=SO_CONTEXT),
    }
    opts.update(options)
    expanded = pyld.jsonld.expand(doc, opts)

    # Determine which context to apply
    is_https = isHttpsSchemaOrg(expanded)
    context_map = SO_CONTEXT
    if is_https:
        context_map = SOS_CONTEXT
    opts = {
        "documentLoader": localRequestsDocumentLoader(context_map=context_map),
    }

    # Compact the schema.org elements of the document
    context = {"@context": "https://schema.org/"}
    return pyld.jsonld.compact(expanded, context, opts)


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


def sosoNormalize(doc, options={}):
    """
    Return JSONLD document expanded and using SOSO recommendations.

    The JSON-LD is set to use a remote reference to the schema.org context
    and expanded using a modified version of the schema.org context to
    set the @container for certain elements to be @list.

    Args:
        doc: JSONLD
        options: pyld.jsonld.expand options

    Returns:
        expanded JSONLD with http://schema.org/ and @list for certain elements
    """
    newdoc = switchToHttpSchemaOrg(doc, options=options)
    sosodoc = addSchemaOrgListContainer(newdoc)
    return sosodoc


def sosoDatasetFrame(expanded, options={}):
    """
    Return a SOSO JSONLD document framed from a Dataset perspective

    Args:
        expanded:

    Returns:

    """
    frame_doc = copy.deepcopy(SO_DATASET_FRAME)
    opts = {
        "documentLoader": localRequestsDocumentLoader(context_map=SOL_CONTEXT),
    }
    opts.update(options)
    fdoc = pyld.jsonld.frame(expanded, frame_doc, options=opts)
    return fdoc
