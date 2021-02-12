"""
Extract JSON-LD
"""
import logging
import flask
import pyld
import requests
import json
import rpyc
from . import utils
from . import normalize

jldex = flask.Blueprint("jldex", __name__, template_folder="templates/jldex")


class objdict(dict):
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


def loadJsonLD(url):
    _L = logging.getLogger("loadJsonLD")
    resp = requests.get(url)
    try:
        jsonld = json.loads(resp.content)
        return jsonld, resp
    except Exception as e:
        _L.warning(e)
    jsonld = pyld.jsonld.load_html(
        resp.content,
        resp.url,
        profile=None,
        options={"extractAllScripts": True},
    )
    return jsonld, resp


def responseSummary(resp):
    def dtdsecs(t):
        return t.seconds + t.microseconds / 1000000.0

    rs = {"rows":[]}
    elapsed = 0.0
    for r in resp.history:
        row = {
            "url": r.url,
            "status_code": r.status_code,
            "content_type": r.headers.get("Content-Type", "-"),
            "last-modified": r.headers.get("Last-Modified", "-"),
            "result": None,
            "elapsed": dtdsecs(r.elapsed),
        }
        elapsed += dtdsecs(r.elapsed)

        loc = r.headers.get("Location", None)
        if loc is not None:
            row["result"] = f"Location: {loc}"
        else:
            row["result"] = "<< body >>"
        rs["rows"].append(row)
    r = resp
    row = {
        "url": r.url,
        "status_code": r.status_code,
        "content_type": r.headers.get("Content-Type", "-"),
        "last-modified": r.headers.get("Last-Modified", "-"),
        "result": None,
        "elapsed": dtdsecs(r.elapsed),
    }
    elapsed += dtdsecs(r.elapsed)
    rs["elapsed"] = elapsed
    loc = r.headers.get("Location", None)
    if loc is not None:
        row["result"] = f"Location: {loc}"
    else:
        row["result"] = "<< body >>"
    rs["rows"].append(row)
    return rs


def jentrify(jbytes):
    try:
        cli = rpyc.connect("localhost", 9991, config={"allow_all_attrs": True})
    except ConnectionRefusedError as e:
        flask.current_app.logger.error("Jentrify service not running: %s", e)
        return []
    proxy = cli.root.jentrify(jbytes)
    result = rpyc.utils.classic.obtain(proxy)
    cli.close()
    return result

@jldex.route(
    "/",
    methods=[
        "HEAD",
        "GET",
    ],
)
def default():
    url = flask.request.args.get("url", None)
    data = objdict()
    data.url = None
    if not url is None:
        data.url = url
        data.hashes = None
        data.jbytes = None
        data.ids = None
        data.jsonld, jresp = normalize.downloadJson(url)
        data.html = jresp.text
        data.jresp = responseSummary(jresp)

        normalizer = normalize.SoNormalize()
        (
            data.jsonld_4,
            data.jsonld_3,
            data.jsonld_2,
            data.jsonld_1,
        ) = normalizer.normalizeSchemaOrg(data.jsonld)
        data.ids = normalize.extractIdentifiers(data.jsonld_4)
        data.hashes, jbytes = utils.jsonChecksums(data.jsonld_4)
        data.jbytes = jbytes.decode()
        data.indexed = jentrify(jbytes)

    response = flask.make_response(flask.render_template("jldex.html", data=data))
    return response, 200
