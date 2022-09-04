"""
Implements jld command line tool for JSON-LD
"""

import sys
import os
import logging
import logging.config
import copy
import json
import click
import shortuuid
import requests
import pyld.jsonld
import c14n
import html
import sonormal
import sonormal.utils
import sonormal.getjsonld
import sonormal.normalize
import sonormal.checksums

logging_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(name)s:%(levelname)s: %(message)s",
            "dateformat": "%Y-%m-%dT%H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "standard",
            "stream": "ext://sys.stderr",
        },
        "socket": {
            "class": "logging.handlers.SocketHandler",
            "level": "DEBUG",
            "host": "localhost",
            "port": 9020,
        },
    },
    "loggers": {
        "": {
            "handlers": [
                "console",
            ],
            "level": "INFO",
            "propogate": False,
        },
        "sonormal": {"level": "INFO"},
        "urllib3": {
            "level": "WARNING",
        },
        "websockets": {
            "level": "ERROR",
        },
        "pyppeteer": {
            "level": "ERROR",
        },
    },
}

LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
    "FATAL": logging.CRITICAL,
    "CRITICAL": logging.CRITICAL,
}


def getLogger():
    return logging.getLogger("so")


def logResponseInfo(resp):
    meta = sonormal.getjsonld.responseSummary(resp)
    logging.info(json.dumps(meta, indent=2))


@click.group()
@click.pass_context
@click.option("-W", "--webpage", is_flag=True, help="Render SPA page")
@click.option("-r", "--response", is_flag=True, help="Show response information")
@click.option("-b", "--base", envvar="SO_BASE", default=None, help="Base URI")
@click.option("-p", "--profile", default=None, help="JSON-LD Profile")
@click.option("-P", "--request-profile", default=None, help="JSON-LD Request Profile")
@click.option("--verbosity", default="INFO", help="Logging level")
def main(ctx, webpage, response, base, profile, request_profile, verbosity):
    verbosity = verbosity.upper()
    logging_config["loggers"][""]["level"] = verbosity
    logging_config["loggers"]["sonormal"]["level"] = verbosity
    logging.config.dictConfig(logging_config)

    ctx.ensure_object(dict)
    sonormal.prepareSchemaOrgLocalContexts()
    document_cache = sonormal.DOCUMENT_CACHE
    fallback_loader = sonormal.requests_document_loader_history()
    documentLoader = sonormal.localRequestsDocumentLoader(
        context_map=sonormal.SO_CONTEXT,
        document_cache=document_cache,
        fallback_loader=fallback_loader,
    )
    ctx.obj["render"] = webpage
    ctx.obj["show_response"] = response
    ctx.obj["base"] = base
    ctx.obj["profile"] = profile
    ctx.obj["request_profile"] = request_profile
    ctx.obj["documentLoader"] = documentLoader


def _getDocument(
    input,
    render=False,
    profile=None,
    requestProfile=None,
    documentUrl=sonormal.DEFAULT_BASE,
    documentLoader=None,
):
    def _jsonldFromString(_src):
        try:
            return json.loads(_src)
        except Exception as e:
            L.warning("Unable to parse input as JSON-LD, trying HTML")
        try:
            options = {"base": doc["documentUrl"], "extractAllScripts": True}
            return pyld.jsonld.load_html(_src, doc["documentUrl"], profile, options)
        except Exception as e:
            L.error("Unable to load JSON-LD")
            L.error(e)
        return None

    L = getLogger()
    doc = {
        "document": None,
        "documentUrl": documentUrl,
        "contextUrl": None,
        "contentType": "",
        "filename": sonormal.utils.fileNameFromURL(documentUrl, "application/ld+json"),
        "response": {},
    }
    # piped input?
    if not sys.stdin.isatty():
        _src = sys.stdin.read()
        doc["document"] = _jsonldFromString(_src)
    else:
        if input is None:
            return doc
        # input is a http URL?
        prot = input[:4].lower()
        if prot in ["http"]:
            doc = sonormal.getjsonld.downloadJson(
                input,
                try_jsrender=render,
                profile=profile,
                requestProfile=requestProfile,
                documentLoader=documentLoader,
            )
        else:
            # input is a filename?
            input = os.path.expanduser(input)
            if not os.path.exists(input):
                L.error("Unable to open source: %s", input)
                return
            _src = None
            with open(input, "r") as src:
                _src = src.read()
            doc["document"] = _jsonldFromString(_src)
        doc["filename"] = sonormal.utils.fileNameFromURL(
            doc["documentUrl"], doc["contentType"]
        )
    return doc


@main.command("cache-clear")
@click.pass_context
def clearCache(ctx):
    L = getLogger()
    for k in sonormal.DOCUMENT_CACHE:
        L.info("Delete cache entry: %s", k)
        sonormal.DOCUMENT_CACHE.delete(k)


@main.command("cache-list")
@click.pass_context
def cacheList(ctx):
    L = getLogger()
    i = 0
    for k in sonormal.DOCUMENT_CACHE:
        # hack to get date added of items
        sql = "SELECT store_time, access_time FROM Cache WHERE key=?"
        _rows = sonormal.DOCUMENT_CACHE._sql(sql, (k,))
        ((t0, t1),) = _rows
        print(
            f"{sonormal.utils.datetimeToJsonStr(sonormal.utils.datetimeFromSomething(t0))} {k}"
        )
        i += 1


@main.command(
    "get",
    help="Retrieve JSON-LD from JSON-LD or HTML document from stdin, disk file, or URL",
)
@click.option("-e", "--expand", is_flag=True, help="Expand the graph")
@click.option(
    "-s", "--sohttp", is_flag=True, help="Adjust to use http://schema.org/ namespace"
)
@click.option(
    "-S",
    "--soso",
    is_flag=True,
    help="Inject @list for ordering certain properties (implies expand)",
)
@click.option("-c", "--canonicalize", is_flag=True, help="Canonicalize JSON-LD")
@click.argument("source", required=False)
@click.pass_context
def getJsonld(ctx, expand, sohttp, soso, canonicalize, source=None):
    L = getLogger()
    doc = _getDocument(
        source,
        render=ctx.obj.get("render", True),
        profile=ctx.obj.get("profile", None),
        requestProfile=ctx.obj.get("request_profile", None),
        documentLoader=ctx.obj.get("documentLoader", None),
    )
    if ctx.obj["show_response"]:
        logResponseInfo(doc["response"])
    options = {
        "base": doc["documentUrl"],
    }
    if not ctx.obj["base"] is None:
        L.info("Overriding base of %s with %s", doc["documentUrl"], ctx.obj["base"])
        options["base"] = ctx.obj["base"]
    if soso:
        so_doc = sonormal.sosoNormalize(doc["document"], options=options)
        doc["document"] = so_doc
    # Don't output whitespace at the end of the document when being
    # piped since it will alter checksums.
    _pend = ""
    if sys.stdout.isatty():
        _pend = "\n"
    elif sohttp:
        so_doc = sonormal.switchToHttpSchemaOrg(doc["document"], options=options)
        doc["document"] = so_doc
    if expand:
        doc["document"] = pyld.jsonld.expand(doc["document"], options=options)
    if canonicalize:
        c_doc = c14n.canonicalize(doc["document"])
        print(c_doc.decode("utf-8"), end=_pend)
    else:
        print(json.dumps(doc["document"], indent=2, sort_keys=True), end=_pend)


@main.command("nquads", help="Output the JSON-LD from SOURCE in N-Quads format")
@click.argument("source", required=False)
@click.pass_context
def toNquads(ctx, source=None):
    L = getLogger()
    doc = _getDocument(
        source,
        render=ctx.obj.get("render", True),
        profile=ctx.obj.get("profile", None),
        requestProfile=ctx.obj.get("request_profile", None),
        documentLoader=ctx.obj.get("documentLoader", None),
    )
    if doc["document"] is None:
        L.error("No document loaded from %s", input)
        return
    options = {"format": sonormal.MEDIA_NQUADS, "base": doc["documentUrl"]}
    if not ctx.obj["base"] is None:
        L.info("Overriding base of %s with %s", doc["documentUrl"], ctx.obj["base"])
        options["base"] = ctx.obj["base"]
    _pend = ""
    if sys.stdout.isatty():
        _pend = "\n"
    print(pyld.jsonld.to_rdf(doc["document"], options=options), end=_pend)


@main.command(
    "canon",
    help="Normalize the JSON-LD from SOURCE by applying URDNA2015 "
    + "and render as JSON-LD in canonical form as per RFC 8785",
)
@click.argument("source", required=False)
@click.pass_context
def canonicalizeJsonld(ctx, source=None):
    L = getLogger()
    doc = _getDocument(
        source,
        render=ctx.obj.get("render", True),
        profile=ctx.obj.get("profile", None),
        requestProfile=ctx.obj.get("request_profile", None),
        documentLoader=ctx.obj.get("documentLoader", None),
    )
    if doc["document"] is None:
        L.error("No document loaded from %s", source)
        return
    options = {"base": doc["documentUrl"]}
    if not ctx.obj["base"] is None:
        L.info("Overriding base of %s with %s", doc["documentUrl"], ctx.obj["base"])
        options["base"] = ctx.obj["base"]
    ndoc = sonormal.normalize.normalizeJsonld(doc["document"], options=options)
    cdoc = sonormal.normalize.canonicalizeJson(ndoc)
    _pend = ""
    if sys.stdout.isatty():
        _pend = "\n"
    print(cdoc, end=_pend)


@main.command("frame", help="Apply frame to source (default = Dataset)")
@click.argument("source", required=False)
@click.option("-f", "--frame", default=None, help="Path to frame document")
@click.pass_context
def frameJsonld(ctx, source=None, frame=None):
    L = getLogger()
    doc = _getDocument(
        source,
        render=ctx.obj.get("render", True),
        profile=ctx.obj.get("profile", None),
        requestProfile=ctx.obj.get("request_profile", None),
        documentLoader=ctx.obj.get("documentLoader", None),
    )
    if doc["document"] is None:
        L.error("No document loaded from %s", input)
        return
    options = {"base": doc["documentUrl"]}
    if not ctx.obj["base"] is None:
        L.info("Overriding base of %s with %s", doc["documentUrl"], ctx.obj["base"])
        options["base"] = ctx.obj["base"]
    frame_doc = None
    if frame is not None:
        res = _getDocument(frame)
        frame_doc = res.get("document", None)
        if frame_doc is None:
            L.warning("Could not load frame document %s", frame)
    if frame_doc is None:
        frame_doc = oc = copy.deepcopy(sonormal.SO_DATASET_FRAME)
        L.warning("Defaulting to SO Dataset frame")
    cdoc = pyld.jsonld.frame(doc["document"], frame=frame_doc, options=options)
    print(json.dumps(cdoc, indent=2, sort_keys=True))


@main.command(
    "identifiers",
    help="Get document identifiers and optionally compute checksums for canonical form.",
)
@click.argument("source", required=False)
@click.option("-c", "--checksums", is_flag=True, help="Compute checksums")
@click.pass_context
def datasetIdentifiers(ctx, source=None, checksums=False):
    """
    Extracts identifiers from JSON-Ld containing schema.org/Dataset

    Args:
        ctx: click context
        source: stdin, file path, or URL for JSON-LD source
        checksums: Calculate checksums on canonical form of JSON-LD

    Returns:
        Array of dict
    """
    L = getLogger()
    doc = _getDocument(
        source,
        render=ctx.obj.get("render", True),
        profile=ctx.obj.get("profile", None),
        requestProfile=ctx.obj.get("request_profile", None),
        documentLoader=ctx.obj.get("documentLoader", None),
    )
    if doc["document"] is None:
        L.error("No document loaded from %s", input)
        return
    options = {"base": doc["documentUrl"]}
    if not ctx.obj["base"] is None:
        L.info("Overriding base of %s with %s", doc["documentUrl"], ctx.obj["base"])
        options["base"] = ctx.obj["base"]
    ndoc = sonormal.normalize.normalizeJsonld(doc["document"], options=options)
    cdoc = sonormal.normalize.frameSODataset(ndoc)
    ids = sonormal.normalize.getDatasetsIdentifiers(cdoc)
    if checksums:
        ids[0]["checksums"], _ = sonormal.checksums.jsonChecksums(ndoc)
    print(json.dumps(ids, indent=2, sort_keys=True))


@main.command("compact", help="Compact the JSON-LD SOURCE")
@click.argument("source", required=False)
@click.option("-c", "--context", default=None, help="Context document to use")
@click.pass_context
def compactJsonld(ctx, source=None, context=None):
    L = getLogger()
    doc = _getDocument(
        source,
        render=ctx.obj.get("render", True),
        profile=ctx.obj.get("profile", None),
        requestProfile=ctx.obj.get("request_profile", None),
        documentLoader=ctx.obj.get("documentLoader", None),
    )
    if doc["document"] is None:
        L.error("No document loaded from %s", input)
        return
    options = {"base": doc["documentUrl"]}
    cdoc = sonormal.normalize.compactSODataset(
        doc["document"], options=options, context=context
    )
    print(json.dumps(cdoc, indent=2, sort_keys=True))


@main.command("play")
@click.argument("source", required=False)
@click.pass_context
def jsonldPlayground(ctx, source=None):
    raise NotImplementedError("Play is not implemented")
    L = getLogger()
    doc = _getDocument(
        source,
        render=ctx.obj.get("render", True),
        profile=ctx.obj.get("profile", None),
        requestProfile=ctx.obj.get("request_profile", None),
    )
    if doc["document"] is None:
        L.error("No document loaded from %s", input)
        return
    url = "https://hastebin.com/documents"
    data = {"data": doc["document"]}
    res = requests.post(url, data=data, timeout=5)
    print(res.text)


@main.command("info")
@click.argument("source", required=False)
@click.pass_context
def jsonldInfo(ctx, source=None):
    """
    Compute information about the JSON-LD

    Args:
        ctx:
        source:

    Returns:
        dict
    """
    L = getLogger()
    doc = _getDocument(
        source,
        render=ctx.obj.get("render", True),
        profile=ctx.obj.get("profile", None),
        requestProfile=ctx.obj.get("request_profile", None),
        documentLoader=ctx.obj.get("documentLoader", None),
    )
    if doc["document"] is None:
        L.error("No document loaded from %s", input)
        return
    # Checksum on original form
    original_checksums, doc_bytes = sonormal.checksums.jsonChecksums(
        doc["document"], canonicalize=False
    )
    # Checksums on canonical form
    checksums, doc_bytes = sonormal.checksums.jsonChecksums(
        doc["document"], canonicalize=True
    )
    _framed = sonormal.normalize.frameSODataset(doc["document"])
    identifiers = sonormal.normalize.getDatasetsIdentifiers(_framed)
    info = {
        "size": len(doc_bytes),
        "source_md5": original_checksums["md5"],
        "checksums": checksums,
        "identifiers": identifiers,
    }
    print(json.dumps(info, indent=2, sort_keys=True))


@main.command("publish")
@click.option("--dryrun", is_flag=True, help="Dry run, just show sysmeta and object")
@click.option("--jwt", envvar="SO_JWT", default=None, help="JWT for authenticating (SO_JWT)")
@click.option(
    "-m", "--mnode", envvar="SO_MNODE", help="Member Node base URL (SO_MNODE)"
)
@click.option(
    "-M", "--nodeid", envvar="SO_MNODE_ID", help="Membernode ID (SO_MNODE_ID)"
)
@click.option(
    "-S", "--submitter", envvar="SO_SUBMITTER", help="Submitter identity (SO_SUBMITTER)"
)
@click.option(
    "-R",
    "--rholder",
    default=None,
    envvar="SO_RIGHTS_HOLDER",
    help="Rights holder identity, defaults to submitter (SO_RIGHTS_HOLDER)",
)
@click.option(
    "--ignore_seriesid",
    is_flag=True,
    help="Publish even if SeriesId can not be determined from JSON-LD."
)
@click.argument("source", required=False)
@click.pass_context
def jsonldPublish(ctx, dryrun, jwt, mnode, nodeid, submitter, rholder, ignore_seriesid, source=None):
    """
    curl -v
    -H "Authorization: Bearer ${JWT}"
    -F "pid=sha256:eb0ec7dfa1c1e6e6d5edae852f53ca326526eb481ba59f90ffe5f7c18a971fd8X"
    -F "object=@dryad.1ms70.jsonld"
    -F "sysmeta=@dryad.1ms70.xml"
    "https://mn-sandbox-ucsb-2.test.dataone.org/knb/d1/mn/v2/object"
    Args:
        ctx:
        dryrun:
        jwt:
        mnode:
        nodeid:
        submitter:
        rholder:
        source:

    Returns:

    """
    L = getLogger()
    if rholder is None:
        L.info("Setting rights holder to submitter (%s)", submitter)
        rholder = submitter
    doc = _getDocument(
        source,
        render=ctx.obj.get("render", True),
        profile=ctx.obj.get("profile", None),
        requestProfile=ctx.obj.get("request_profile", None),
        documentLoader=ctx.obj.get("documentLoader", None),
    )
    if doc["document"] is None:
        L.error("No document loaded from %s", input)
        return
    # System metadata checksum on original form
    original_checksums, doc_bytes = sonormal.checksums.jsonChecksums(
        doc["document"], canonicalize=False
    )
    # Checksums on canonical form
    checksums, doc_bytes = sonormal.checksums.jsonChecksums(
        doc["document"], canonicalize=True
    )

    # get identifiers from a document framed as SO Dataset
    iddoc = sonormal.switchToHttpSchemaOrg(doc["document"])
    _framed = sonormal.normalize.frameSODataset(iddoc)
    identifiers = sonormal.normalize.getDatasetsIdentifiers(_framed)
    seriesId = ""
    if len(identifiers) > 0:
        ids = identifiers[0]
        if len(ids["identifier"]) > 0:
            seriesId = ids["identifier"][0]
        elif len(ids["@id"]) > 0:
            seriesId = ids["@id"][0]
        elif len(ids["url"]) > 0:
            seriesId = ids["url"][0]
    else:
        L.warning("Could not determine a SeriesId.")
        if not ignore_seriesid:
            L.error("Publication without SeriesId not enabled. Aborting.")
            return 1
    tstamp = sonormal.utils.datetimeToJsonStr(sonormal.utils.dtnow())
    pid = f"sha256:{checksums['sha256']}"
    meta = {
        "pid": pid,
        "size": len(doc_bytes),
        "checksum": original_checksums["md5"],
        "seriesId": seriesId,
        "submitter": submitter,
        "rightsHolder": rholder,
        "dateUploaded": tstamp,
        "dateModified": tstamp,
        "originMemberNode": nodeid,
        "authoritativeMemberNode": nodeid,
        "fileName": doc.get("filename", None),
    }
    if meta["fileName"] is None:
        meta["fileName"] = f"{shortuuid.uuid()}.jsonld"

    sysm = f"""<?xml version="1.0" encoding="UTF-8"?>
<d1:systemMetadata xmlns:d1="http://ns.dataone.org/service/types/v2.0">
  <serialVersion>1</serialVersion>
  <identifier>{meta['pid']}</identifier>
  <seriesId>{html.escape(meta['seriesId'])}</seriesId>
  <formatId>science-on-schema.org/Dataset;ld+json</formatId>
  <size>{meta['size']}</size>
  <checksum algorithm="MD5">{meta['checksum']}</checksum>
  <submitter>{html.escape(meta['submitter'])}</submitter>
  <rightsHolder>{html.escape(meta['rightsHolder'])}</rightsHolder>
  <accessPolicy>
    <allow>
      <subject>public</subject>
      <permission>read</permission>
    </allow>
  </accessPolicy>
  <replicationPolicy numberReplicas="3" replicationAllowed="true"></replicationPolicy>
  <archived>false</archived>
  <dateUploaded>{html.escape(meta['dateUploaded'])}</dateUploaded>
  <dateSysMetadataModified>{html.escape(meta['dateModified'])}</dateSysMetadataModified>
  <originMemberNode>{html.escape(meta['originMemberNode'])}</originMemberNode>
  <authoritativeMemberNode>{html.escape(meta['authoritativeMemberNode'])}</authoritativeMemberNode>
  <mediaType name="application/ld+json"></mediaType>
  <fileName>{html.escape(meta['fileName'])}</fileName>
</d1:systemMetadata>"""
    if dryrun:
        print("PAYLOAD:")
        print(json.dumps(doc["document"], indent=2, sort_keys=True))
        print("SYSTEMMETADATA:")
        print(sysm)
        return 0
    headers = {
        "Accept": "text/xml",
        # "Content-Type": "multipart/form-data",
        "Authorization": f"Bearer {jwt}",
        "User-Agent": "SO 0.3;python 3.9; 202107",
    }
    files = {
        "pid": (None, pid),
        "object": (
            meta["fileName"],
            json.dumps(doc["document"], indent=2, sort_keys=True),
        ),
        "sysmeta": ("sysm.xml", sysm),
    }
    url = f"{mnode}/v2/object"
    L.info("Target URL: %s", url)
    response = requests.post(url, headers=headers, files=files)
    L.debug(response.request.headers)
    L.info("Status: %s", response.status_code)
    L.info("Message: %s", response.text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
