"""
Retrieve JSON-LD from a URL
"""
import logging
import requests
import sonormal
import pyppeteer
import pyld.jsonld

# Wait this long for a browser to render a page
BROWSER_RENDER_TIMEOUT = 5000  # msec


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
    try:
        page = await browser.newPage()
        await page.goto(url)
        # await page.waitForSelector('#Metadata')
        # Give the page 5 seconds for a jsonld to appear
        await page.waitForXPath(
            f'//script[@type="{sonormal.MEDIA_JSONLD}"]', timeout=BROWSER_RENDER_TIMEOUT
        )
        content = await page.content()
        _L.debug("JLD position: %s", content.find("ld+json"))
        jsonld = pyld.jsonld.load_html(
            content,
            url,
            profile=None,
            options={"extractAllScripts": True},
        )
    finally:
        await browser.close()
        _L.debug("Exit downloadJsonRendered")
    return jsonld


def downloadJson(url, headers={}):
    _L = logging.getLogger("sonormal")
    try:
        response = requests.get(url, headers=headers, timeout=20)
    except requests.Timeout as e:
        _L.error("Reques to %s timed out", url)
        return {"ERROR": str(e)}, []
    _L.debug("Final URL = %s", response.url)
    try:
        jsonld = json.loads(response.content)
        return jsonld, response
    except Exception as e:
        _L.warning(e)
    # returns an array of json-ld found in the document
    jsonld = pyld.jsonld.load_html(
        response.content,
        response.url,
        profile=None,
        options={"extractAllScripts": True},
    )
    if len(jsonld) < 1:
        # Empty array?
        # try loading and rendering the page
        jsonld = asyncio.run(downloadJsonRendered(url))
    return jsonld, response
