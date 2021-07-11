import os
import sonormal
import tempfile
import json
import logging

logging.basicConfig(level=logging.DEBUG)

def test_prepareSchemaOrgLocalContexts():
    with tempfile.TemporaryDirectory() as dest_folder:
        paths = sonormal.prepareSchemaOrgLocalContexts(dest_folder, refresh=True)
        for k in paths:
            assert os.path.exists(paths[k])
        with open(paths["so"]) as inf:
            o = json.load(inf)
            assert o.get("@context", {}).get("@vocab") == "http://schema.org/"
            assert o.get("@context", {}).get("schema") == "http://schema.org/"
        with open(paths["sol"]) as inf:
            o = json.load(inf)
            assert o.get("@context", {}).get("@vocab") == "http://schema.org/"
            assert o.get("@context", {}).get("schema") == "http://schema.org/"
            assert o.get("@context", {}).get("creator", {}).get("@container") == "@list"
            assert o.get("@context", {}).get("identifier", {}).get("@container") == "@list"
            assert o.get("@context", {}).get("description", {}).get("@container") == "@list"
        with open(paths["sos"]) as inf:
            o = json.load(inf)
            assert o.get("@context", {}).get("@vocab") == "https://schema.org/"
            assert o.get("@context", {}).get("schema") == "https://schema.org/"

