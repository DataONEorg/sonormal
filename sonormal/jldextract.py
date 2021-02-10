"""
Extract JSON-LD
"""
import os
import logging
import flask
import copy
import pyld
import requests
import json
import tempfile
import utils
import opersist.rdfutils
import glob
import jnius_config
import xml.etree.ElementTree as ET

_classpath_base = "apache-jena-3.17.0/lib/"
_jars = ["."]
for jar in glob.glob(f"{_classpath_base}*.jar"):
    _jars.append(jar)
try:
    jnius_config.set_classpath(*_jars)
except:
    pass
from jnius import autoclass


jldex = flask.Blueprint("jldex", __name__, template_folder="templates/jldex")

QUERY_SOURCE = "https://raw.githubusercontent.com/DataONEorg/d1_cn_index_processor/develop_2.3/src/main/resources/application-context-schema-org.xml"
SPARQL_QUERIES = {}

def loadSparqlQueries(query_source):
    queries = {}
    ns = {
        "b": "http://www.springframework.org/schema/beans",
    }
    bean_config = ET.fromstring(requests.get(query_source).text)
    beans = bean_config.findall("b:bean", ns)
    for bean in beans:
        cargs = bean.findall("./b:constructor-arg", ns)
        qname = None
        q = None
        for carg in cargs:
            if carg.attrib["name"] == "name":
                qname = carg.attrib["value"]
            elif carg.attrib["name"] == "query":
                q = carg.find("./b:value", ns).text
        if not qname is None:
            queries[qname] = q.strip()
    return queries

SPARQL_QUERIES = loadSparqlQueries(QUERY_SOURCE)


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
    rs = []
    for r in resp.history:
        row = {
            "url": r.url,
            "status_code":r.status_code,
            "content_type": r.headers.get('Content-Type', '-'),
            "last-modified": r.headers.get('Last-Modified', '-'),
            "result": None,
        }

        loc = r.headers.get("Location", None)
        if loc is not None:
            row["result"] = f"Location: {loc}"
        else:
            row["result"] = "<< body >>"
        rs.append(row)
    r = resp
    row = {
        "url": r.url,
        "status_code": r.status_code,
        "content_type": r.headers.get('Content-Type', '-'),
        "last-modified": r.headers.get('Last-Modified', '-'),
        "result": None
    }
    loc = r.headers.get("Location", None)
    if loc is not None:
        row["result"] = f"Location: {loc}"
    else:
        row["result"] = "<< body >>"
    rs.append(row)
    return rs

def jentrify(jsonld, queries):
    dataManager = autoclass('org.apache.jena.riot.RDFDataMgr')
    queryFactory = autoclass('org.apache.jena.query.QueryFactory')
    queryExecutionFactory = autoclass('org.apache.jena.query.QueryExecutionFactory')
    tmpf = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonld")
    fname = tmpf.name
    tmpf.write(jsonld)
    tmpf.close()
    dataset = dataManager.loadDataset(fname)
    idxresults = []
    for term, query in queries.items():
        row = {
            "query": query,
            "term": term,
            "v": []
        }
        q = queryFactory.create(query)
        qexec = queryExecutionFactory.create(q, dataset)
        results = qexec.execSelect()
        for res in results:
            v = res.get(term)
            if not v is None:
                row["v"].append(v.toString())
            else:
                row["v"].append(res.toString())
        idxresults.append(row)
    os.unlink(fname)
    return idxresults

@jldex.record
def record(state):
    """
    Called when a m_node blueprint is being registered.
    Args:
        state: The state information for the BluePrint

    Returns: nothing

    """
    L = logging.getLogger("m_node.record")
    name = state.options.get("mnode_name")
    L.debug("MNODE name = %s", name)


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
        data.jsonld, jresp = loadJsonLD(url)
        data.html = jresp.text
        data.jresp = responseSummary(jresp)

        data.jsonld_1 = pyld.jsonld.expand(data.jsonld)
        ctx = {"@context": {"@vocab": "http://schema.org/"}}
        opts = {"graph": True, "compactArrays": True, "ordered": True}
        data.jsonld_2 = pyld.jsonld.compact(data.jsonld_1, ctx, options=opts)

        data.jsonld_3 = copy.deepcopy(data.jsonld_2)
        data.jsonld_3["@context"]["@vocab"] = "https://schema.org/"

        ctxs = copy.deepcopy(data.jsonld_3["@context"])
        ctxs["https://schema.org/creator"] = {"@container": "@list"}
        ctxs["https://schema.org/identifier"] = {"@container": "@list"}
        data.jsonld_4 = pyld.jsonld.compact(data.jsonld_3, ctxs, options=opts)

        ctxs = copy.deepcopy(data.jsonld_4["@context"])
        data.jsonld_5 = pyld.jsonld.compact(data.jsonld_4, ctxs, options=opts)

        data.ids = opersist.rdfutils.extractIdentifiers(data.jsonld_5)
        data.hashes, jbytes = opersist.utils.jsonChecksums(data.jsonld_5)
        data.jbytes = jbytes.decode()

        data.indexed = jentrify(jbytes, SPARQL_QUERIES)

    response = flask.make_response(flask.render_template("jldex.html", data=data))
    return response, 200
