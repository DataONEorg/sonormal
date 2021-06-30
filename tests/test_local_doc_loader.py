import os
import pytest
import sonormal
import tempfile
import json
import atexit
import shutil
import pyld

class LocalContexts:
    def __init__(self, url, doc):
        self.dest_folder = tempfile.mkdtemp()
        self.dest_fname = os.path.join(self.dest_folder, "context.jsonld")
        atexit.register(self.cleanup)
        with open(self.dest_fname, "w") as dest:
            json.dump(doc, dest)
        self.cmap = {url: self.dest_fname}

    def cleanup(self):
        shutil.rmtree(self.dest_folder)


@pytest.fixture
def example_context():
    url = "https://example.net/some_random_thing"
    doc = {
        "@context": {
            "@vocab": "https://example.net/test/",
            "t": "https://example.net/test/",
            "TEST": {"@id": "t:TEST"},
        }
    }
    return LocalContexts(url, doc)


@pytest.fixture
def example_doc():
    doc = {"@context": "https://example.net/some_random_thing", "TEST": "Test value"}
    return doc


def test_localContext(example_context, example_doc):
    # Map the URL to a local context file
    options = {
        "documentLoader": sonormal.localRequestsDocumentLoader(context_map=example_context.cmap)
    }
    expanded = pyld.jsonld.expand(example_doc, options)
    k = "https://example.net/test/TEST"
    assert k in expanded[0].keys()
    v = expanded[0].get(k,[{}])[0].get("@value")
    assert v == "Test value"


def test_noLocalContext(example_doc):
    # This should fail since the context does not exist
    try:
        expanded = pyld.jsonld.expand(example_doc)
    except Exception as e:
        assert isinstance(e, pyld.jsonld.JsonLdError)

