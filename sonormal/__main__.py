"""
Implements jld command line tool for JSON-LD
"""

import sys
import os
import logging
import logging.config
import json
import click
import requests
import pyld.jsonld
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
                "socket",
            ],
            "level": "DEBUG",
            "propogate": False,
        },
        "sonormal": {"level": "DEBUG"},
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
    return logging.getLogger("jld")


def logResponseInfo(resp):
    meta = sonormal.getjsonld.responseSummary(resp)
    logging.info(json.dumps(meta, indent=2))


@click.group()
@click.pass_context
@click.option("-W", "--webpage", is_flag=True, help="Render SPA page")
@click.option("-r", "--response", is_flag=True, help="Show response information")
@click.option("-b", "--base", default=None, help="Base URI")
@click.option("-p", "--profile", default=None, help="JSON-LD Profile")
@click.option("-P", "--request-profile", default=None, help="JSON-LD Request Profile")
@click.option(
    "--soprod",
    is_flag=True,
    help="Use schema.org production context instead of v12 https",
)
def main(ctx, webpage, response, base, profile, request_profile, soprod):
    ctx.ensure_object(dict)
    logging.config.dictConfig(logging_config)
    if soprod:
        sonormal.FORCE_SO_VERSION = False
    sonormal.installDocumentLoader()
    ctx.obj["render"] = webpage
    ctx.obj["show_response"] = response
    ctx.obj["base"] = base
    ctx.obj["profile"] = profile
    ctx.obj["request_profile"] = request_profile


def _getDocument(input, render=False, profile=None, requestProfile=None):
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
        "documentUrl": sonormal.DEFAULT_BASE,
        "contextUrl": None,
        "contentType": "",
        "response": {},
    }
    if not sys.stdin.isatty():
        _src = sys.stdin.read()
        doc["document"] = _jsonldFromString(_src)
    else:
        if input is None:
            return doc
        prot = input[:4].lower()
        if prot in ["http"]:
            doc = sonormal.getjsonld.downloadJson(
                input,
                try_jsrender=render,
                profile=profile,
                requestProfile=requestProfile,
            )
        else:
            input = os.path.expanduser(input)
            if not os.path.exists(input):
                L.error("Unable to open source: %s", input)
                return
            _src = None
            with open(input, "r") as src:
                _src = src.read()
            doc["document"] = _jsonldFromString(_src)
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
        #hack to get date added of items
        sql = "SELECT store_time, access_time FROM Cache WHERE key=?"
        _rows = sonormal.DOCUMENT_CACHE._sql(sql, (k, ))
        ((t0, t1),) = _rows
        print(f"{sonormal.utils.datetimeToJsonStr(sonormal.utils.datetimeFromSomething(t0))} {k}")
        i += 1

@main.command(
    "get",
    help="Retrieve JSON-LD from JSON-LD or HTML document from stdin, disk file, or URL",
)
@click.option("-e", "--expand", is_flag=True, help="Expand the graph")
@click.argument("source")
@click.pass_context
def getJsonld(ctx, expand, source=None):
    L = getLogger()
    doc = _getDocument(
        source,
        render=ctx.obj.get("render", True),
        profile=ctx.obj.get("profile", None),
        requestProfile=ctx.obj.get("request_profile", None),
    )
    if ctx.obj["show_response"]:
        logResponseInfo(doc["response"])
    options = {
        "base": doc["documentUrl"],
    }
    if not ctx.obj["base"] is None:
        L.info("Overriding base of %s with %s", doc["documentUrl"], ctx.obj["base"])
        options["base"] = ctx.obj["base"]
    if expand:
        doc["document"] = pyld.jsonld.expand(doc["document"], options=options)
    print(json.dumps(doc["document"], indent=2))


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
    )
    if doc["document"] is None:
        L.error("No document loaded from %s", input)
        return
    options = {"format": sonormal.MEDIA_NQUADS, "base": doc["documentUrl"]}
    if not ctx.obj["base"] is None:
        L.info("Overriding base of %s with %s", doc["documentUrl"], ctx.obj["base"])
        options["base"] = ctx.obj["base"]
    print(pyld.jsonld.to_rdf(doc["document"], options=options))


@main.command(
    "canon",
    help="Normalize the JSON-LD from SOURCE by applying URDNA2015 and render as JSON-LD in canonical form as per RFC 8785",
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
    print(cdoc)


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
    ndoc = sonormal.normalize.normalizeJsonld(doc["document"], options=options)
    cdoc = sonormal.normalize.frameSODataset(ndoc, frame_doc=frame_doc)
    print(json.dumps(cdoc, indent=2))


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
        ids[0]["hashes"], _ = sonormal.checksums.jsonChecksums(ndoc)
    print(json.dumps(ids, indent=2))


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
    )
    if doc["document"] is None:
        L.error("No document loaded from %s", input)
        return
    options = {"base": doc["documentUrl"]}
    cdoc = sonormal.normalize.compactSODataset(doc["document"], options=options, context=context)
    print(json.dumps(cdoc, indent=2))


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

if __name__ == "__main__":
    sys.exit(main())
