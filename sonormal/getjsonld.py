"""
Retrieve JSON-LD from a URL
"""
import logging
import datetime
import json
import requests
import asyncio
import pyld.jsonld
import pyppeteer
import sonormal

# Wait this long for a browser to render a page
BROWSER_RENDER_TIMEOUT = 10000  # msec



#
# Replacement for pyld.jsonld.load_document for use with web pages.
# The original defaults to JSON-LD parsing if the content-type is not
# explicitly a html type. Here we try parsing the response as JSON and
# falling back to the html loader regardless of what the proposed content
# type is.



#TODO: set reqeust headers in rendered request
async def downloadJsonRendered(url):
    _L = logging.getLogger("sonormal")
    _L.debug("Loading and rendering %s", url)
    # TODO: Should really be a single browser or pool of them rather than recreating
    # Actually, this is the preferred mode for doing this stuff:
    # 1. Only launch a browser when needed
    # 2. Get rid of it when done, fresh per request is better for longevity
    browser = await pyppeteer.launch(
        handleSIGINT=False, handleSIGTERM=False, handleSIGHUP=False
    )
    jsonld = []
    response = sonormal.ObjDict({
        "url": url,
        "history": [],
        "status_code": 0,
        "headers": {},
        "text": None,
        "elapsed": datetime.timedelta(),
    })
    try:
        page = await browser.newPage()
        _response = await page.goto(url)
        response["url"] = _response.url
        response["status_code"] = _response.status
        response["headers"] = _response.headers
        for _history in _response.request.redirectChain:
            h = sonormal.ObjDict({
                "url": _history.response.url,
                "status_code": _history.response.status,
                "headers": _history.response.headers,
                "text": None,
                "elapsed": datetime.timedelta(),
            })
            response["history"].append(h) 
        # await page.waitForSelector('#Metadata')
        # Give the page 5 seconds for a jsonld to appear
        await page.waitForXPath(
            f'//script[@type="{sonormal.MEDIA_JSONLD}"]', timeout=BROWSER_RENDER_TIMEOUT
        )
        content = await page.content()
        response["text"] = content
        _L.debug("JLD position: %s", content.find("ld+json"))
        jsonld = pyld.jsonld.load_html(
            content,
            url,
            profile=None,
            options={"extractAllScripts": True},
        )
    except Exception as e:
        _L.error(e)
    finally:
        await browser.close()
        _L.debug("Exit downloadJsonRendered")
    return jsonld, response


def downloadJson(url, headers={}, try_jsrender=True):
    _L = logging.getLogger("sonormal")
    headers.setdefault("Accept", sonormal.DEFAULT_REQUEST_ACCEPT_HEADERS)
    try:
        options = {
            "headers": headers,
            "documentLoader": pyld.jsonld.get_document_loader()
        }
        response_doc = pyld.jsonld.load_document(url, options)
        jsonld = response_doc["document"]
        response = response_doc["response"]
        return jsonld, response
    except requests.Timeout as e:
        _L.error("Request to %s timed out", url)
        return {"ERROR": str(e)}, []
    except pyld.jsonld.JsonLdError as e:
        _L.warning("No JSON-LD in plain source %s", url)
        if not try_jsrender:
            raise(e)
        # Empty array?
        # try loading and rendering the page
        jsonld, response = asyncio.run(downloadJsonRendered(url))
    return jsonld, response
