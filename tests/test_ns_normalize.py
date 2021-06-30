import os
import pytest
import sonormal
import tempfile
import atexit
import shutil
import json
import pyld


class LocalContexts:
    def __init__(self):
        self.dest_folder = tempfile.mkdtemp()

        self.dest_fname = os.path.join(self.dest_folder, "context.jsonld")
        sonormal.prepareSchemaOrgLocalContexts(context_folder=self.dest_folder)
        atexit.register(self.cleanup)

    def cleanup(self):
        shutil.rmtree(self.dest_folder)


@pytest.fixture(scope="module")
def soContext():
    return LocalContexts()


def test_vocab(soContext):
    doc = {"@context": {"@vocab": "https://schema.org/"}, "name": "test value"}
    tdoc = sonormal.switchToHttpSchemaOrg(doc)
    assert tdoc.get("@context") in sonormal.SCHEMA_ORG_CONTEXT_URLS
    options = {
        "documentLoader": sonormal.localRequestsDocumentLoader(sonormal.SO_CONTEXT)
    }
    edoc = pyld.jsonld.expand(tdoc, options)
    v = edoc[0].get("http://schema.org/name", [{}])[0].get("@value")
    assert v == "test value"


def test_remote(soContext):
    doc = {"@context": "https://schema.org/", "name": "test value"}
    tdoc = sonormal.switchToHttpSchemaOrg(doc)
    assert tdoc.get("@context") in sonormal.SCHEMA_ORG_CONTEXT_URLS
    options = {
        "documentLoader": sonormal.localRequestsDocumentLoader(sonormal.SO_CONTEXT)
    }
    edoc = pyld.jsonld.expand(tdoc, options)
    v = edoc[0].get("http://schema.org/name", [{}])[0].get("@value")
    assert v == "test value"


def test_prefix(soContext):
    doc = {"@context": {"so": "https://schema.org/"}, "so:name": "test value"}
    tdoc = sonormal.switchToHttpSchemaOrg(doc)
    assert tdoc.get("@context") in sonormal.SCHEMA_ORG_CONTEXT_URLS
    options = {
        "documentLoader": sonormal.localRequestsDocumentLoader(sonormal.SO_CONTEXT)
    }
    edoc = pyld.jsonld.expand(tdoc, options)
    v = edoc[0].get("http://schema.org/name", [{}])[0].get("@value")
    assert v == "test value"
