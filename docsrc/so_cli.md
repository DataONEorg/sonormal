`so` cli
========

`so` is a commandline tool that enables retrieval of JSON-LD, some processing options for the JSON-LD, and ability to publish the JSON-LD to the DataONE federation.

```
so
Usage: so [OPTIONS] COMMAND [ARGS]...

Options:
  -W, --webpage               Render SPA page
  -r, --response              Show response information
  -b, --base TEXT             Base URI
  -p, --profile TEXT          JSON-LD Profile
  -P, --request-profile TEXT  JSON-LD Request Profile
  --soprod                    Use schema.org production context instead of v12
                              https

  --help                      Show this message and exit.

Commands:
  cache-clear
  cache-list
  canon        Normalize the JSON-LD from SOURCE by applying URDNA2015 and...
  compact      Compact the JSON-LD SOURCE
  frame        Apply frame to source (default = Dataset)
  get          Retrieve JSON-LD from JSON-LD or HTML document from stdin,...
  identifiers  Get document identifiers and optionally compute checksums
               for...

  nquads       Output the JSON-LD from SOURCE in N-Quads format
  play
```