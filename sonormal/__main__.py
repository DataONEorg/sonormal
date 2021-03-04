"""
Implements jld command line tool for JSON-LD
"""

import sys
import os
import logging
import logging.config
import json
import click
import pyld.jsonld
import sonormal
import sonormal.getjsonld
import sonormal.normalize

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
def main(ctx, webpage):
    ctx.ensure_object(dict)
    logging.config.dictConfig(logging_config)
    sonormal.installDocumentLoader()
    ctx.obj["render"] = webpage


@main.command("get")
@click.argument("url")
@click.option(
    "-f",
    "--format",
    type=click.Choice(["jsonld", "nquads"], case_sensitive=False),
    default="jsonld",
    help="Output format",
)
@click.option("-r", "--response", is_flag=True, help="Show response information")
@click.pass_context
def getJsonld(ctx, url, format, response):
    L = getLogger()
    doc = sonormal.getjsonld.downloadJson(url, try_jsrender=ctx.obj["render"])
    if response:
        logResponseInfo(doc["response"])
    if format == "nquads":
        print(pyld.jsonld.to_rdf(doc["document"], {"format": sonormal.MEDIA_NQUADS}))
    else:
        print(json.dumps(doc["document"], indent=2))


def _getDocument(input, render=False, profile=None, requestProfile=None):
    L = getLogger()
    doc = {
        "document": None,
        "documentUrl": sonormal.DEFAULT_BASE,
        "contextUrl": None,
        "contentType": "",
        "response": {},
    }
    if input == "-":
        doc["document"] = json.load(sys.stdin)
    else:
        prot = input[:4].lower()
        if prot in ["http"]:
            doc = sonormal.getjsonld.downloadJson(
                input,
                try_jsrender=render,
                profile=profile,
                requestProfile=requestProfile,
            )
        else:
            if not os.path.exists(input):
                L.error("Unable to open source: %s", input)
                return
            with open(input, "r").read() as src:
                doc["document"] = json.load(src)
    return doc


@main.command("canon")
@click.argument("input")
@click.pass_context
def canonicalizeJsonld(ctx, input):
    L = getLogger()
    doc = _getDocument(input, render=ctx.obj["render"])
    if doc["document"] is None:
        L.error("No document loaded from %s", input)
        return
    ndoc = sonormal.normalize.normalizeJsonld(doc["document"])
    cdoc = sonormal.normalize.canonicalizeJson(ndoc)
    print(cdoc)


@main.command("frame")
@click.argument("input")
@click.pass_context
def frameJsonld(ctx, input):
    L = getLogger()
    doc = _getDocument(input, render=ctx.obj["render"])
    if doc["document"] is None:
        L.error("No document loaded from %s", input)
        return
    ndoc = sonormal.normalize.normalizeJsonld(doc["document"])
    cdoc = sonormal.normalize.frameSODataset(ndoc)
    print(json.dumps(cdoc, indent=2))


if __name__ == "__main__":
    sys.exit(main())
