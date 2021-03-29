"""
Retrieve JSON-LD from a URL
"""
import time
import logging
import datetime
import json
import requests
import asyncio
import pyld.jsonld
import pyppeteer
import sonormal
import sonormal.utils

# Wait this long for a browser to render a page
BROWSER_RENDER_TIMEOUT = 10000  # msec

__L = logging.getLogger("sonormal.getjsonld")


def responseSummary(resp):
    """
    JSON-able conversion of requests response info dict

    Args:
        resp: A requests response-like thing

    Returns:
        dict

    """

    def dtdsecs(t):
        return t.seconds + t.microseconds / 1000000.0

    def httpDateToJson(d):
        if d is None:
            return d
        dt = sonormal.utils.datetimeFromSomething(d)
        return sonormal.utils.datetimeToJsonStr(dt)

    elapsed = 0.0

    def addHistory(r):
        row = {
            "url": r.url,
            "status_code": r.status_code,
            "result": None,
            "elapsed": dtdsecs(r.elapsed),
            "headers": {},
        }
        for k in r.headers:
            row["headers"][k.lower()] = r.headers.get(k)

        row["content_type"] = row["headers"].get("content-type", None)
        row["last_modified"] = httpDateToJson(row["headers"].get("last-modified", None))
        row["date"] = httpDateToJson(row["headers"].get("date", None))

        nonlocal elapsed
        elapsed += dtdsecs(r.elapsed)

        loc = r.headers.get("Location", None)
        if loc is not None:
            row["result"] = f"Location: {loc}"
        else:
            row["result"] = "<< body >>"
        return row

    rs = {
        "request": {},
        "responses": [],
        "resources_loaded": [],
    }
    try:
        rs["resources_loaded"] = resp.resources_loaded
    except AttributeError as e:
        pass
    rs["request"]["url"] = resp.request.url
    rs["request"]["headers"] = {}
    for k in resp.request.headers:
        rs["request"]["headers"][k] = resp.request.headers.get(k)
    for r in resp.history:
        rs["responses"].append(addHistory(r))
    rs["responses"].append(addHistory(resp))
    return rs


# TODO: set request headers in rendered request
async def downloadJsonRendered(url, headers={}, profile=None, requestProfile=None):
    __L.debug("Loading and rendering %s", url)
    # TODO: Handle response link headers. This should not be necessary here unless
    # using this method as the primary mechanism for making the request, which is
    # not advisable because of the overhead. Only fallback to this after trying with
    # the non-rendered approach, and that should catch any link headers in the response.

    # TODO: Should really be a single browser or pool of them rather than recreating
    # Actually, this is the preferred mode for doing this stuff:
    # 1. Only launch a browser when needed
    # 2. Get rid of it when done, fresh per request is better for longevity

    timers = {}

    def startRequest(request, **kwargs):
        nonlocal timers
        timers[request.url] = time.time()
        __L.debug(str(request.url))
        __L.debug(str(request.headers))

    def responseDone(response, **kwargs):
        __L.debug("RESPONSE URL= %s", response.url)
        __L.debug("RESPONSE HEADERS: %s", str(response.headers))
        t1 = time.time()
        nonlocal timers
        t0 = timers.get(response.url, t1)
        timers[response.url] = t1 - t0

    doc = {
        "contentType": None,
        "contextUrl": None,
        "documentUrl": None,
        "document": None,  # document is parsed later
        "response": None,  # Include the response for history/performance review
    }

    browser = await pyppeteer.launch(
        handleSIGINT=False, handleSIGTERM=False, handleSIGHUP=False
    )
    response = sonormal.ObjDict(
        {
            "url": url,
            "history": [],
            "status_code": 0,
            "headers": {},
            "text": None,
            "elapsed": datetime.timedelta(),
            "request": sonormal.ObjDict(
                {
                    "headers": {},
                    "url": url,
                }
            ),
        }
    )
    try:
        page = await browser.newPage()
        if requestProfile is not None:
            accept = headers.get('Accept', sonormal.DEFAULT_REQUEST_ACCEPT_HEADERS)
            headers["Accept"] = f"application/ld+json;profile={requestProfile}, {accept}"

        await page.setExtraHTTPHeaders(headers)
        page.on("request", startRequest)
        page.on("response", responseDone)
        __L.debug("PAGE GOTO")
        _response = await page.goto(url)

        # await page.waitForSelector('#Metadata')
        # Give the page 5 seconds for a jsonld to appear
        try:
            __L.debug("PAGE WAIT XPATH")
            await page.waitForXPath(
                f'//script[@type="{sonormal.MEDIA_JSONLD}"]', timeout=BROWSER_RENDER_TIMEOUT
            )
        except Exception as e:
            __L.error(e)
        __L.debug("PAGE WAIT CONTENT")
        content = await page.content()
        __L.debug("PAGE LOADED")

        # Gather metadata about the request and responses
        response.request.headers = _response.request.headers
        response["url"] = _response.url
        response["status_code"] = _response.status
        response["headers"] = _response.headers
        doc["contentType"] = response["headers"].get(
            "content-type", sonormal.DEFAULT_RESPONSE_CONTENT_TYPE
        )
        doc["documentUrl"] = response.url

        for _history in _response.request.redirectChain:
            h = sonormal.ObjDict(
                {
                    "url": _history.response.url,
                    "status_code": _history.response.status,
                    "headers": _history.response.headers,
                    "text": None,
                }
            )
            h.elapsed = datetime.timedelta(seconds=timers.get(h["url"], 3))
            response["history"].append(h)

        response["elapsed"] = datetime.timedelta(seconds=timers.get(_response.url, 3))
        response["resources_loaded"] = list(timers.keys())

        # Extract the JSON-LD from the page
        response["text"] = content
        __L.debug("JLD position: %s", content.find("ld+json"))
        jsonld = pyld.jsonld.load_html(
            content,
            doc["documentUrl"],
            profile=profile,
            options={"extractAllScripts": True},
        )
        doc["document"] = jsonld
        doc["response"] = response
    except Exception as e:
        __L.error(e)
    finally:
        await browser.close()
        __L.debug("Exit downloadJsonRendered")
    return doc


def downloadJson(url, headers={}, profile=None, requestProfile=None, try_jsrender=True):
    headers.setdefault("Accept", sonormal.DEFAULT_REQUEST_ACCEPT_HEADERS)
    try:
        options = {
            "headers": headers,
            "documentLoader": pyld.jsonld.get_document_loader(),
        }
        response_doc = pyld.jsonld.load_document(
            url, options, profile=profile, requestProfile=requestProfile
        )
        return response_doc
    except requests.Timeout as e:
        __L.error("Request to %s timed out", url)
        return {"ERROR": str(e)}
    except pyld.jsonld.JsonLdError as e:
        __L.warning("No JSON-LD in plain source %s", url)
        if not try_jsrender:
            raise (e)
        # Empty array?
        # try loading and rendering the page
        response_doc = asyncio.run(
            downloadJsonRendered(
                url, headers=headers, profile=profile, requestProfile=requestProfile
            )
        )
    return response_doc


async def downloadJsonAsync(url, headers={}, try_jsrender=True):
    """
    Not really async, just running without creating an event loop.
    Args:
        url: URL to retrieve from
        headers: Optional headers to use in request
        try_jsrender: Use the pyppeteer page renderer if needed

    Returns:
        json-ld document, requests response (or similar)
    """
    headers.setdefault("Accept", sonormal.DEFAULT_REQUEST_ACCEPT_HEADERS)
    try:
        options = {
            "headers": headers,
            "documentLoader": pyld.jsonld.get_document_loader(),
        }
        response_doc = pyld.jsonld.load_document(url, options)
        return response_doc
    except requests.Timeout as e:
        __L.error("Request to %s timed out", url)
        return {"ERROR": str(e)}, []
    except pyld.jsonld.JsonLdError as e:
        __L.warning("No JSON-LD in plain source %s", url)
        if not try_jsrender:
            raise (e)
        # Empty array?
        # try loading and rendering the page
        response_doc = await downloadJsonRendered(url, headers=headers)
    return response_doc
