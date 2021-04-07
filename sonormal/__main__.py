"""
Implements jld command line tool for JSON-LD
"""

import sys
import os
import logging
import logging.config
import json
import click
import urllib
import subprocess
import webbrowser
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
@click.option("-b", "--base", default=None, help="Base URI")
@click.option("-p", "--profile", default=None, help="JSON-LD Profile")
@click.option("-P", "--request-profile", default=None, help="JSON-LD Request Profile")
@click.option("-r", "--response", is_flag=True, help="Show response information")
@click.option(
    "-R", "--relaxed-json", is_flag=True, help="Relax strict JSON deserialization"
)
@click.option("-W", "--webpage", is_flag=True, help="Render SPA page")
@click.option(
    "--soprod",
    is_flag=True,
    help="Use schema.org production context instead of v12 https",
)
def main(ctx, webpage, response, base, profile, request_profile, soprod, relaxed_json):
    """Retrieve and process JSON-LD."""
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
    ctx.obj["json_parse_strict"] = not relaxed_json


def _getDocument(
    input, render=False, profile=None, requestProfile=None, json_parse_strict=True
):
    def _jsonldFromString(_src, _json_parse_strict=True):
        try:
            return json.loads(_src, strict=_json_parse_strict)
        except Exception as e:
            L.warning("Unable to parse input as JSON-LD, trying HTML")
        try:
            options = {
                "base": doc["documentUrl"],
                "extractAllScripts": True,
                "json_parse_strict": _json_parse_strict,
            }
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
        doc["document"] = _jsonldFromString(_src, _json_parse_strict=json_parse_strict)
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
                json_parse_strict=json_parse_strict,
            )
        else:
            input = os.path.expanduser(input)
            if not os.path.exists(input):
                L.error("Unable to open source: %s", input)
                return
            _src = None
            with open(input, "r") as src:
                _src = src.read()
            doc["document"] = _jsonldFromString(
                _src, _json_parse_strict=json_parse_strict
            )
    return doc


@main.command("cache", short_help="Cache management, list or purge")
@click.option("-p", "--purge", is_flag=True, help="Purge the cache")
@click.pass_context
def cacheList(ctx, purge):
    '''Manage the downloaded document cache (~/.local/sonormal/cache/)
    '''
    L = getLogger()
    if purge:
        for k in sonormal.DOCUMENT_CACHE:
            L.info("Delete cache entry: %s", k)
            sonormal.DOCUMENT_CACHE.delete(k)
        return
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
    short_help="Retrieve JSON-LD",
)
@click.option("-e", "--expand", is_flag=True, help="Expand the graph")
@click.argument("source")
@click.pass_context
def getJsonld(ctx, expand, source=None):
    '''Retrieve JSON-LD from JSON-LD or HTML document from stdin, disk file, or URL. 

    Downloaded content is cached to avoid repeated download when performing
    multiple operations on the same document.
    '''
    L = getLogger()
    doc = _getDocument(
        source,
        render=ctx.obj.get("render", True),
        profile=ctx.obj.get("profile", None),
        requestProfile=ctx.obj.get("request_profile", None),
        json_parse_strict=ctx.obj.get("json_parse_strict", True),
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


@main.command("nquads", short_help="Transform JSON-LD to N-Quads")
@click.argument("source", required=False)
@click.pass_context
def toNquads(ctx, source=None):
    '''Output the JSON-LD from SOURCE in N-Quads format
    '''
    L = getLogger()
    doc = _getDocument(
        source,
        render=ctx.obj.get("render", True),
        profile=ctx.obj.get("profile", None),
        requestProfile=ctx.obj.get("request_profile", None),
        json_parse_strict=ctx.obj.get("json_parse_strict", True),
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
    short_help="Normalize and render canonical form",
)
@click.argument("source", required=False)
@click.pass_context
def canonicalizeJsonld(ctx, source=None):
    '''Normalize the JSON-LD from SOURCE by applying URDNA2015 and 
    render as JSON-LD in canonical form as per RFC 8785
    '''
    L = getLogger()
    doc = _getDocument(
        source,
        render=ctx.obj.get("render", True),
        profile=ctx.obj.get("profile", None),
        requestProfile=ctx.obj.get("request_profile", None),
        json_parse_strict=ctx.obj.get("json_parse_strict", True),
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


@main.command("frame", short_help="Apply frame to source")
@click.argument("source", required=False)
@click.option("-f", "--frame", default=None, help="Path to frame document")
@click.pass_context
def frameJsonld(ctx, source=None, frame=None):
    '''Apply frame to SOURCE using JSON-LD framing. 

    Default frame is SO_DATASET_FRAME in __init__.py
    '''
    L = getLogger()
    doc = _getDocument(
        source,
        render=ctx.obj.get("render", True),
        profile=ctx.obj.get("profile", None),
        requestProfile=ctx.obj.get("request_profile", None),
        json_parse_strict=ctx.obj.get("json_parse_strict", True),
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
    short_help="Extract Dataset identifiers",
)
@click.argument("source", required=False)
@click.option("-c", "--checksums", is_flag=True, help="Compute checksums")
@click.pass_context
def datasetIdentifiers(ctx, source=None, checksums=False):
    """
    Extracts identifiers from JSON-Ld containing schema.org/Dataset
    \f

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
        json_parse_strict=ctx.obj.get("json_parse_strict", True),
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


@main.command("compact", short_help="Compact the JSON-LD SOURCE")
@click.argument("source", required=False)
@click.option("-c", "--context", default=None, help="Context document to use")
@click.pass_context
def compactJsonld(ctx, source=None, context=None):
    '''Apply JSON-LD compacting algorithm to SOURCE.

    Default context = {"@context": ["https://schema.org/", {"id": "id", "type": "type"}]}
    '''
    L = getLogger()
    doc = _getDocument(
        source,
        render=ctx.obj.get("render", True),
        profile=ctx.obj.get("profile", None),
        requestProfile=ctx.obj.get("request_profile", None),
        json_parse_strict=ctx.obj.get("json_parse_strict", True),
    )
    if doc["document"] is None:
        L.error("No document loaded from %s", input)
        return
    options = {"base": doc["documentUrl"]}
    cdoc = sonormal.normalize.compactSODataset(
        doc["document"], options=options, context=context
    )
    print(json.dumps(cdoc, indent=2))


@main.command("play", short_help="Load in JSON-LD Playground")
@click.option("-B", "--browser", "open_browser", is_flag=True, help="Open playground in browser")
@click.argument("source", required=False)
@click.pass_context
def jsonldPlayground(ctx, open_browser, source=None):
    '''Creates a public Github Gist from SOURCE and loads to JSON-LD Playground.

    Requires the "gh" command is available and authenticated.
    '''
    import subprocess

    L = getLogger()
    doc = _getDocument(
        source,
        render=ctx.obj.get("render", True),
        profile=ctx.obj.get("profile", None),
        requestProfile=ctx.obj.get("request_profile", None),
        json_parse_strict=ctx.obj.get("json_parse_strict", True),
    )
    if doc["document"] is None:
        L.error("No document loaded from %s", input)
        return
    cmd = ["gh","gist","create", "-p"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout_data, stderr_data = p.communicate(input=json.dumps(doc["document"], indent=2).encode("UTF-8"))
    res = stdout_data.decode().strip()
    if not res.startswith("https://"):
        print(f"Could not create gh gist: \n{stdout_data}")
        return
    response = requests.get(res)
    print(f"New public gist created at:\n  {response.url}")
    url = response.url.replace("https://gist.github.com/", "https://gist.githubusercontent.com/",1)
    url = url + "/raw"
    #print(url)
    PG = "https://json-ld.org/playground/#startTab=tab-expanded&json-ld="
    url = PG + urllib.parse.quote(url, safe='')
    print(f"Link to JSON-LD playground:\n  {url}")
    if open_browser:
        webbrowser.open(url, new=2)


@main.command("valid", short_help="Validate with SHACL")
@click.pass_context
def shaclValidate(ctx, source=None, shacl=None):
    L = getLogger()
    doc = _getDocument(
        source,
        render=ctx.obj.get("render", True),
        profile=ctx.obj.get("profile", None),
        requestProfile=ctx.obj.get("request_profile", None),
        json_parse_strict=ctx.obj.get("json_parse_strict", True),
    )
    if doc["document"] is None:
        L.error("No document loaded from %s", input)
        return
    if shacl is None:
        shacl = "https://raw.githubusercontent.com/ESIPFed/science-on-schema.org/master/validation/shapegraphs/soso_common_v1.2.2.ttl"
    shacl_src = requests.get(shacl).text
    service_url = "https://ti921zid2b.execute-api.us-east-1.amazonaws.com/dev/verify"
    data = {
        "fmt":"json-ld",
        "infer": False,        
    }
    files = {
        "sg": ("sg.ttl", shacl_src, "application/turtle"),
        "dg": ("dg.jsonld", json.dumps(doc["document"], indent=2), "application/ld+json"),
    }
    response = requests.post(service_url, files=files, data=data)
    print(response.text)



if __name__ == "__main__":
    sys.exit(main())
