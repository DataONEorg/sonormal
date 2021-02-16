import os
import logging
import tempfile
import requests
import glob
import time
import xml.etree.ElementTree as ET
import rpyc
import jnius_config

_classpath_base = "apache-jena-3.17.0/lib/"
_jars = ["."]
for jar in glob.glob(f"{_classpath_base}*.jar"):
    _jars.append(jar)
try:
    jnius_config.add_options("-Djava.awt.headless=true")
    jnius_config.set_classpath(*_jars)
except:
    pass
from jnius import autoclass

QUERY_SOURCE = "https://raw.githubusercontent.com/DataONEorg/d1_cn_index_processor/develop_2.3/src/main/resources/application-context-schema-org.xml"
QCACHE_MAX_AGE = 30.0 #seconds


class JenqlService(rpyc.Service):
    def __init__(self, *args, **kwargs):
        self.sparql_url = kwargs.pop("sparql_url")
        super().__init__(*args, **kwargs)
        self._sparql_loaded = 0.0
        self._sparql_queries = self._loadSparqlQueries(self.sparql_url)

    def on_connect(self, conn):
        pass

    def on_disconnect(self, conn):
        pass

    def _loadSparqlQueries(self, query_source):
        L = logging.getLogger("_loadSparqlQueries")
        queries = {}
        t = time.time()
        if t - self._sparql_loaded < QCACHE_MAX_AGE:
            if len(queries) > 1:
                L.info("Ignoring cache refresh")
                return
        self._sparql_loaded = t
        L.info("Refreshing SPARQL cache from source")
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

    def _jentrify(self, jsonld):
        L = logging.getLogger("jentrify")
        L.debug("Starting jentrify...")
        self._loadSparqlQueries(self.sparql_url)
        try:
            dataManager = autoclass("org.apache.jena.riot.RDFDataMgr")
            queryFactory = autoclass("org.apache.jena.query.QueryFactory")
            queryExecutionFactory = autoclass(
                "org.apache.jena.query.QueryExecutionFactory"
            )
        except Exception as e:
            L.error(e)
            return []
        tmpf = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonld")
        fname = tmpf.name
        tmpf.write(jsonld)
        tmpf.close()
        L.debug("jentrify fname= %s", fname)
        dataset = dataManager.loadDataset(fname)
        L.debug("dataset loaded")
        idxresults = []
        for term, query in self._sparql_queries.items():
            L.debug("Running query %s", term)
            row = {"query": query, "term": term, "v": []}
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

    def exposed_jentrify(self, jbytes):
        if isinstance(jbytes, str):
            jbytes = jbytes.encode("utf-8")
        return self._jentrify(jbytes)


def main():
    logging.basicConfig(level=logging.DEBUG)
    server = rpyc.utils.server.ThreadedServer(
        JenqlService(sparql_url=QUERY_SOURCE),
        port=9991,
        protocol_config={"allow_public_attrs": True, "allow_pickle": True},
    )
    server.start()


if __name__ == "__main__":
    main()
