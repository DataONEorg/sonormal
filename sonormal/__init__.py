import logging
import requests
import re
import string
import pyld.jsonld
import pyppeteer
import urllib.parse as urllib_parse

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
SO_PROPERTY_ID = f"{SO_}propertyID"

SO_COMPACT_CONTEXT = {
    "@context": [
        "https://schema.org/",
        {
            "id":"id",
            "type":"type"
        }
    ]
}

SO_DATASET_FRAME = {
    "@context": "https://schema.org/",
    "@type": "Dataset",
    "identifier": {},
    "creator": {},
}

# regexp to match the typical location of the schema.org remote context
SO_MATCH = re.compile(r"http(s)?\://schema.org(/)?")

# Location of the schema.org context document
SO_CONTEXT_LOCATION = "https://raw.githubusercontent.com/schemaorg/schemaorg/main/data/releases/12.0/schemaorgcontext.jsonld"


# Timeout for the document loader requests
REQUEST_TIMEOUT = 30 #seconds

# Default content type when not provided in server response
# pyld defaults to application/octet-stream, which makes sense
# but means sloppy HTML responses are not handled in load_document()
DEFAULT_RESPONSE_CONTENT_TYPE = "text/html"

# Content negotiation support is pretty bad. This *should* work, but will
# not be respected on some services. It's generally OK to fall back to
# application/ld+json or text/html or even */*, though should be applied
# consistently per target.
DEFAULT_REQUEST_ACCEPT_HEADERS = "application/ld+json;q=1.0, application/json;q=0.9, text/html;q=0.8, application/xml+xhtml;q=0.7"

# TODO: use a real cache
DOCUMENT_CACHE = {}


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
    import requests

    def loader(url, options={}):
        """
        Retrieves JSON-LD at the given URL.
        :param url: the URL to retrieve.
        :return: the RemoteDocument.
        """
        L = logging.getLogger("loader")
        L.debug("ENTER: loader")
        try:
            # validate URL
            pieces = urllib_parse.urlparse(url)
            if (not all([pieces.scheme, pieces.netloc]) or
                    pieces.scheme not in ['http', 'https'] or
                    set(pieces.netloc) > set(
                        string.ascii_letters + string.digits + '-.:')):
                raise pyld.jsonld.JsonLdError(
                    'URL could not be dereferenced; only "http" and "https" '
                    'URLs are supported.',
                    'jsonld.InvalidUrl', {'url': url},
                    code='loading document failed')
            if secure and pieces.scheme != 'https':
                raise pyld.jsonld.JsonLdError(
                    'URL could not be dereferenced; secure mode enabled and '
                    'the URL\'s scheme is not "https".',
                    'jsonld.InvalidUrl', {'url': url},
                    code='loading document failed')
            headers = options.get('headers')
            if headers is None:
                headers = {
                    'Accept': 'application/ld+json, application/json'
                }

            response = requests.get(url, headers=headers, **kwargs)

            content_type = response.headers.get('content-type')
            if not content_type:
                content_type = DEFAULT_RESPONSE_CONTENT_TYPE
            doc = {
                'contentType': content_type,
                'contextUrl': None,
                'documentUrl': response.url,
                'document': None,    #document is parsed later
                'response': None,    #Include the response for history/performance review
            }
            link_header = response.headers.get('link')
            if link_header:
                linked_context = pyld.jsonld.parse_link_header(link_header).get(
                    pyld.jsonld.LINK_HEADER_REL)
                # only 1 related link header permitted when matching for context
                if linked_context and content_type != 'application/ld+json':
                    if isinstance(linked_context, list):
                        raise pyld.jsonld.JsonLdError(
                            'URL could not be dereferenced, '
                            'it has more than one '
                            'associated HTTP Link Header.',
                            'jsonld.LoadDocumentError',
                            {'url': url},
                            code='multiple context link headers')
                    doc['contextUrl'] = linked_context['target']
                linked_alternate = pyld.jsonld.parse_link_header(link_header).get('alternate')
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
                            L.debug("CANDIDATE Link: %s", candidate)
                            if candidate.get('type') == 'application/ld+json':
                                if _profile is not None:
                                    if candidate.get('profile') == _profile:
                                        the_linked_alternate = candidate
                                        break
                                else:
                                    the_linked_alternate = candidate
                                    break
                    else:
                        the_linked_alternate = linked_alternate
                if (the_linked_alternate and
                        the_linked_alternate.get('type') == 'application/ld+json' and
                        not re.match(r'^application\/(\w*\+)?json$', content_type)):
                    doc['contentType'] = 'application/ld+json'
                    doc['documentUrl'] = pyld.jsonld.prepend_base(url, the_linked_alternate['target'])
                    # recurse into loader with the new URL
                    return loader(doc['documentUrl'], options=options)
            # parse the json response and return
            # Do not parse JSON here. It needs to be done in load_document to handle the
            # situation where JSON-LD needs to be extracted from a HTML response.
            #doc['document'] = response.json()
            doc['document'] = response.text
            doc['response'] = response
            return doc
        except pyld.jsonld.JsonLdError as e:
            raise e
        except Exception as cause:
            raise pyld.jsonld.JsonLdError(
                'Could not retrieve a JSON-LD document from the URL.',
                'jsonld.LoadDocumentError', code='loading document failed',
                cause=cause)
    return loader


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
    options.setdefault("timeout", REQUEST_TIMEOUT)
    options.setdefault("allow_redirects", True)
    loader = requests_document_loader_history(timeout=options.get("timeout"), allow_redirects=options.get("allow_redirects"))
    resp = loader(url, options=options)
    DOCUMENT_CACHE[url] = resp
    return resp


# Patch the new document loader into pyld
pyld.jsonld.set_document_loader(cachingDocumentLoader)
