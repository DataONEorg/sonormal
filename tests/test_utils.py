import pytest
import sonormal.utils

url_name_tests = [
    [{"url": None, "content_type": None}, None],
    [{"url": "nothing", "content_type": None}, "nothing.bin"],
    [{"url": "nothing", "content_type": ""}, "nothing.bin"],
    [{"url": "https://example.net/test.txt", "content_type": "text/plain"}, "test.txt"],
    [
        {"url": "https://example.net/test.txt", "content_type": "application/json"},
        "test.txt.json",
    ],
    [
        {"url": "https://example.net/test.txt", "content_type": "application/ld+json"},
        "test.txt.jsonld",
    ],
    [
        {
            "url": "https://www.hydroshare.org/resource/e827b87bbd74497fbfeac33921cc084d/#schemaorg",
            "content_type": "text/html",
        },
        "e827b87bbd74497fbfeac33921cc084d.html",
    ],
    [
        {
            "url": "https://doi.org/10.5061/dryad.q778387",
            "content_type": "application/ld+json"
        },
        "dryad.q778387.jsonld"
    ],
    [
        {
            "url":"https://datadryad.org/stash/dataset/doi%253A10.5061%252Fdryad.q778387",
            "content_type": "application/ld+json"
        },
        "doi%3A10.5061%2Fdryad.q778387.jsonld"
    ],
    [
        {
            "url":"http://datadryad.org/api/v2/datasets/doi%253A10.5061%252Fdryad.q778387/download",
            "content_type": "application/octet-stream"
        },
        "doi%3A10.5061%2Fdryad.q778387.bin"
    ],
    [
        {
            "url":"http://lod.bco-dmo.org/id/dataset/3093",
            "content_type": "application/ld+json",
        },
        "3093.jsonld"
    ],
    [
        {
            "url": "http://lod.bco-dmo.org/id/dataset/3093?a=4&b=5",
            "content_type": "application/ld+json",
        },
        "3093.jsonld"
    ],
]


@pytest.mark.parametrize("inp, expected", url_name_tests)
def test_filenameFromUrl(inp, expected):
    res = sonormal.utils.fileNameFromURL(inp["url"], inp["content_type"])
    assert res == expected
