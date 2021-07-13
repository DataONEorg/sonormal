import logging
import pytest
import tempfile
import json
import orjson
import pyld.jsonld
import sonormal.checksums

# Three copies of the same document serialized differently. Each should
# return the same checksum.
test_checksums = [
    [
        {
            "@context": {
                "@vocab": "https://schema.org/",
                "identifier": {"@container": "@list"},
            },
            "@id": "test_1",
            "@type": "Dataset",
            "identifier": ["test_1", "test_2"],
        },
        {
            "sha256": "c803622a973175425ed9fbfc23c74fc8bd3b2b130fc2f492571bcb3429f5bc46",
            "sha1": "912f3b2c8e0e1086db4d8ecd6cd61c67e8d50ebe",
            "md5": "0bfb4ca147b1ed72d8cdcf4af015fce2",
        },
    ],
    [
        {
            "@context": [
                "https://schema.org/",
                {"identifier": {"@container": "@list"}},
            ],
            "@id": "test_1",
            "@type": "Dataset",
            "identifier": ["test_1", "test_2"],
        },
        {
            "sha256": "c803622a973175425ed9fbfc23c74fc8bd3b2b130fc2f492571bcb3429f5bc46",
            "sha1": "912f3b2c8e0e1086db4d8ecd6cd61c67e8d50ebe",
            "md5": "0bfb4ca147b1ed72d8cdcf4af015fce2",
        },
    ],
    [
        {
            "@context": ["http://schema.org/", {"identifier": {"@container": "@list"}}],
            "identifier": ["test_1", "test_2"],
            "@id": "test_1",
            "@type": "Dataset",
        },
        {
            "sha256": "c803622a973175425ed9fbfc23c74fc8bd3b2b130fc2f492571bcb3429f5bc46",
            "sha1": "912f3b2c8e0e1086db4d8ecd6cd61c67e8d50ebe",
            "md5": "0bfb4ca147b1ed72d8cdcf4af015fce2",
        },
    ],
]


test_compare = [
    [
        {
            "@context": "https://schema.org/",
            "name": "test_order",
            "identifier": "test_order_id",
            "variableMeasured": [
                {
                    "@type": "PropertyValue",
                    "propertyID": "var_a",
                    "maxValue": 0.00000000001
                },
                {
                    "@type": "PropertyValue",
                    "propertyID": "var_b",
                    "maxValue": 3.14519
                },
            ],
            "description": "These elements are not in order",
        },
        {
            "@context": "https://schema.org/",
            "description": "These elements are not in order",
            "identifier": "test_order_id",
            "name": "test_order",
            "variableMeasured": [
                {
                    "@type": "PropertyValue",
                    "maxValue": 1E-11,
                    "propertyID": "var_a",
                },
                {
                    "maxValue": 0.314519E1,
                    "@type": "PropertyValue",
                    "propertyID": "var_b",
                }
            ],
        },
    ],
]


@pytest.mark.parametrize("doc,expected", test_checksums)
def test_jdonldChecksum(doc, expected):
    with tempfile.TemporaryDirectory() as dest_folder:
        # setup the local context mappings for normalization
        paths = sonormal.prepareSchemaOrgLocalContexts(dest_folder, refresh=False)

        # Ensure schema.org docs are using the same pattern
        cnv_doc = sonormal.switchToHttpSchemaOrg(doc)

        # Expand the document using default document loader
        exp_doc = pyld.jsonld.expand(cnv_doc)
        checksums, _ = sonormal.checksums.jsonChecksums(exp_doc, canonicalize=True)
        assert checksums["sha256"] == expected["sha256"]

        # Expand the document using local cache document loader
        options = {
            "documentLoader": sonormal.localRequestsDocumentLoader(
                context_map=sonormal.SO_CONTEXT
            ),
        }
        exp_doc = pyld.jsonld.expand(cnv_doc, options=options)
        checksums, _ = sonormal.checksums.jsonChecksums(exp_doc, canonicalize=True)
        assert checksums["sha256"] == expected["sha256"]


@pytest.mark.parametrize("a,b", test_compare)
def test_jsonldCompare(a, b):
    with tempfile.TemporaryDirectory() as dest_folder:
        # setup the local context mappings for normalization
        paths = sonormal.prepareSchemaOrgLocalContexts(dest_folder, refresh=False)
        a_cnv = sonormal.switchToHttpSchemaOrg(a)
        b_cnv = sonormal.switchToHttpSchemaOrg(b)
        a_exp = pyld.jsonld.expand(a_cnv)
        b_exp = pyld.jsonld.expand(b_cnv)
        chk_a, _ = sonormal.checksums.jsonChecksums(a_exp)
        chk_b, _ = sonormal.checksums.jsonChecksums(b_exp)
        assert chk_a["sha256"] == chk_b["sha256"]
        chk_a, _ = sonormal.checksums.jsonChecksums(a_exp, canonicalize=False)
        chk_b, _ = sonormal.checksums.jsonChecksums(b_exp, canonicalize=False)
        assert chk_a["sha256"] == chk_b["sha256"]


@pytest.mark.parametrize("a,b", test_compare)
def test_jsonldCompareORJSON(a, b):
    a_exp = pyld.jsonld.expand(a)
    b_exp = pyld.jsonld.expand(b)
    a_bytes = orjson.dumps(a_exp, option=orjson.OPT_SORT_KEYS)
    b_bytes = orjson.dumps(b_exp, option=orjson.OPT_SORT_KEYS)
    chk_a, _ = sonormal.checksums.computeChecksumsBytes(a_bytes)
    chk_b, _ = sonormal.checksums.computeChecksumsBytes(b_bytes)
    assert chk_a["sha256"] == chk_b["sha256"]
