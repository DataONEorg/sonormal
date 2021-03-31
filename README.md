# sonormal

`sonormal` is a python library to assist with extraction and processing of schema.org content with emphasis on the [`Dataset`](https://schema.org/Dataset) class.

Included is a command line tool `jld` for retrieving and extracting JSON-LD from a web page or other resource and performing various operations on JSON-LD.

This library and tool is focussed on supporting Schema.org harvesting for the DataONE infrastructure.

## Operation

Usage: jld [OPTIONS] COMMAND [ARGS]...

```
Options:
  -b, --base TEXT             Base URI
  -p, --profile TEXT          JSON-LD Profile
  -P, --request-profile TEXT  JSON-LD Request Profile
  -r, --response              Show response information
  -R, --relaxed-json          Relax strict JSON deserialization
  -W, --webpage               Render SPA page
  --soprod                    Use schema.org production context instead of v12 https
  --help                      Show this message and exit.

Commands:
  cache        Cache management, list or purge
  canon        Normalize the JSON-LD from SOURCE by applying URDNA2015 and ...
  compact      Compact the JSON-LD SOURCE
  frame        Apply frame to source (default = Dataset)
  get          Retrieve JSON-LD from JSON-LD or HTML document from stdin, ...
  identifiers  Get document identifiers and optionally compute checksums for...
  nquads       Output the JSON-LD from SOURCE in N-Quads format
```

`cache` lists entries in the local cache (in folder `~/.local/sonormal/cache`) and optionally purges entries.

`canon` canonicalizes the source JSON-LD by expanding and applying the URDNA 2015 algorithm, then serializes with ordered terms, no new lines, and no spaces between delimiters. Checksums computed on the result are consistent between various arrangements of the same input source.

`compact` applies the JSON-LD compaction algorithm to the source using the context:
```
{"@context": [
    "https://schema.org/", 
    { 
      "id": "id", 
      "type": "type" 
    }
  ]
}
```

`frame` applies the JSON-LD framing algorithm to structure the JSON-LD for ease of identifier extraction from a `Dataset` instance using the frame:
```
{
    "@context": {"@vocab":"https://schema.org/"},
    "@type": "Dataset",
    "identifier": {},
    "creator": {}
}
```

`get` retrieves the document from a file or URL, following redirects and Link headers as appropriate. Content is extracted from HTML pages, and optionally (with the `-W` flag set) from single page applications where the JSON-LD may be generated on the fly.

`identifiers` extracts `Dataset` identifier values and computes checksums of the JSON-LD.

`nquads` serializes the JSON-LD to N-Quads format.

## Examples

Download and extract JSON-LD from [Hydroshare](https://www.hydroshare.org/):

```
jld get "https://www.hydroshare.org/resource/058d173af80a4784b471d29aa9ad7257/"
{
  "@context": {
    "@vocab": "https://schema.org/",
    "datacite": "http://purl.org/spar/datacite/"
  },
  "@id": "https://www.hydroshare.org/resource/058d173af80a4784b471d29aa9ad7257",
  "url": "https://www.hydroshare.org/resource/058d173af80a4784b471d29aa9ad7257",
  "@type": "Dataset",
  "additionalType": "http://www.hydroshare.org/terms/CompositeResource",
...
```

Download and extract JSON-LD from a DataONE single page application (with JSON-LD rendered by the client):

```
jld -W get "https://search.dataone.org/view/urn%3Auuid%3Add9ad874-ded8-48fe-908a-06732b9a6297"
[
  {
    "@context": {
      "@vocab": "https://schema.org/"
    },
    "@type": "Dataset",
    "@id": "https://dataone.org/datasets/urn%3Auuid%3Add9ad874-ded8-48fe-908a-06732b9a6297",
    "datePublished": "2013-10-23T00:00:00Z",
    "publisher": {
      "@type": "Organization",
      "name": "California Ocean Protection Council Data Repository"
    },
    "identifier": "urn:uuid:dd9ad874-ded8-48fe-908a-06732b9a6297",
...
```

Processing operations can take stdin as input. For example, normalize JSON-LD using the URDNA 2015 algorithm for assigning ids to blank nodes. Note the source is expanded and canonicalized, output is serialized with no new lines and no spaces between delimiters in preparation for calculating checksums. 

```
jld get "https://www.hydroshare.org/resource/058d173af80a4784b471d29aa9ad7257/" | jld canon

[{"@id":"_:c14n0","@type":["http://purl.org/spar/datacite/ResourceIdentifier","https://schema.org/PropertyValue"],
"http://purl.org/spar/datacite/usesIdentifierScheme":[{"@id":"http://purl.org/spar/datacite/
local-resource-identifier-scheme"}],"https://schema.org/propertyId":[{"@value":"UUID"}],"https://schema.org/value":
[{"@value":"uuid:058d173af80a4784b471d29aa9ad7257"}]},{"@id":"_:c14n1","@type":["https://schema.org/Place"],
...
```

Extract identifiers and compute checksums:

```
jld get "https://www.hydroshare.org/resource/058d173af80a4784b471d29aa9ad7257/" | jld identifiers -c
[
  {
    "@id": [
      "https://www.hydroshare.org/resource/058d173af80a4784b471d29aa9ad7257"
    ],
    "url": [
      "https://www.hydroshare.org/resource/058d173af80a4784b471d29aa9ad7257"
    ],
    "identifier": [
      "uuid:058d173af80a4784b471d29aa9ad7257"
    ],
    "hashes": {
      "sha256": "a8cb4e5806045032fc2e7ad0b762336ff76f3792271ddc071c0d8c85d6b69ac5",
      "sha1": "f6abef03156a5adb6d395f385628a2894e7b920e",
      "md5": "03a357ba8043ac734aa3b9e9bb514ff9"
    }
  }
]
```

## Installation

Install using [`poetry`](https://python-poetry.org/). For example:

```
git clone https://github.com/datadavev/sonormal.git
cd sonormal
poetry install
```
Then run using:
```
poetry run jld
```

Alternatively, install into a separately created virtual environment:
```
poetry install
```
Then run like:
```
jld
```
