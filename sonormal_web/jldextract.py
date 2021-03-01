"""
Extract JSON-LD
"""
import logging
import flask
import pyld
import requests
import json
import rpyc
import sonormal.utils
import sonormal.getjsonld
import sonormal.normalize
import sonormal.checksums

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

    rs = {"rows": []}
    elapsed = 0.0
    for r in resp.history:
        row = {
            "url": r.url,
            "status_code": r.status_code,
            "content_type": r.headers.get("Content-Type", "-"),
            "last_modified": r.headers.get("Last-Modified", "-"),
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
        "last_modified": r.headers.get("Last-Modified", "-"),
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
    force_lists = flask.request.args.get("lists", False)
    data = objdict()
    errors = []
    data.url = None
    if not url is None:
        data.url = url
        data.hashes = None
        data.jbytes = None
        data.ids = None
        data.jsonld = None
        data.jsonld_normalized = None
        data.jsonld_framed = None
        data.jsonld_compacted = None
        data.jsonld_canonical = None
        #rheaders = {
        #    "Accept":"application/ld+json"
        #}
        rheaders = {}
        data.jsonld, jresp = sonormal.getjsonld.downloadJson(url, headers=rheaders)
        if force_lists:
            data.jsonld = sonormal.normalize.forceSODatasetLists(data.jsonld)
        data.html = jresp.text
        options = {"base": jresp.url}
        data.jresp = responseSummary(jresp)
        try:
            data.jsonld_normalized = sonormal.normalize.normalizeJsonld(
                data.jsonld, options=options
            )
        except Exception as e:
            errors.append({"at": "normalize", "e": str(e)})
        if data.jsonld_normalized is not None:
            try:
                data.nquads = sonormal.normalize.jsonldToNquads(
                    data.jsonld_normalized, options=options
                )
            except Exception as e:
                errors.append({"at": "nquads", "e": str(e)})
                # raise (e)
            data.jsonld_framed = sonormal.normalize.frameSODataset(
                data.jsonld_normalized
            )

        if data.jsonld_framed is not None:
            data.jsonld_compacted = sonormal.normalize.compactSODataset(
                data.jsonld_framed, options=options
            )
            data.ids = sonormal.normalize.getDatasetsIdentifiers(data.jsonld_framed)

        if data.jsonld_normalized is not None:
            data.hashes, data.jsonld_canonical = sonormal.checksums.jsonChecksums(
                data.jsonld_normalized
            )
            data.indexed = jentrify(data.jsonld_canonical)
            # make canonical string for rendering
            data.jsonld_canonical = data.jsonld_canonical.decode()

    response = flask.make_response(
        flask.render_template("jldex.html", data=data, errors=errors, force_lists=force_lists)
    )
    return response, 200
