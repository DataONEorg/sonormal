import logging
import hashlib
import json
# c14n is provided with pyld
import c14n

HASH_BLOCK_SIZE = 65536


def computeChecksumsBytes(b, sha256=True, sha1=True, md5=True):
    """
    Computes hashes for the provided Bytes

    Args:
        b: bytes

    Returns:
        dict: Dict of calculated hash hex digests
    """
    hashes = {"sha256": None, "sha1": None, "md5": None}
    if sha256:
        hashes["sha256"] = hashlib.sha256(b).hexdigest()
    if sha1:
        hashes["sha1"] = hashlib.sha1(b).hexdigest()
    if md5:
        hashes["md5"] = hashlib.md5(b).hexdigest()
    return hashes, b


def computeChecksumsString(s, sha256=True, sha1=True, md5=True, encoding="UTF-8"):
    b = s.encode(encoding)
    return computeChecksumsBytes(b, sha256=sha256, sha1=sha1, md5=md5)


def jsonChecksums(doc, canonicalize=True):
    """
    Compute checksums for a JSON object.

    The JSON is serialized to UTF-8 text with no indenting, no space between items
    and key-value, and sorted keys.

    If canonicalize, then the JSON canonicalization Scheme rules are applied using
    the c14n implementation provided with pyld.

    Args:
        doc: The JSON structure
        canonicalize(bool): Apply c14n canonicalization to the JSON

    Returns:
        dict of hashes, bytes

    """
    if canonicalize:
        b = c14n.canonicalize(doc)
    else:
        b = json.dumps(doc, indent=2, sort_keys=True).encode("utf-8")
    return computeChecksumsBytes(b)


def computeChecksumsFLO(flo, sha256=True, sha1=True, md5=True):
    """
    Computes hashes for object in file stream.

    Args:
        flo: file like object open for reading

    Returns:
        dict of md5, sha1, sha256 hashes.

    """
    hashes = {"sha256": None, "sha1": None, "md5": None}
    hsha256 = None
    hsha1 = None
    hmd5 = None
    if sha256:
        hsha256 = hashlib.sha256()
    if sha1:
        hsha1 = hashlib.sha1()
    if md5:
        hmd5 = hashlib.md5()
    fbuf = flo.read(HASH_BLOCK_SIZE)
    while len(fbuf) > 0:
        if sha256:
            hsha256.update(fbuf)
        if sha1:
            hsha1.update(fbuf)
        if md5:
            hmd5.update(fbuf)
        fbuf = flo.read(HASH_BLOCK_SIZE)
    if sha256:
        hashes["sha256"] = hsha256.hexdigest()
    if sha1:
        hashes["sha1"] = hsha1.hexdigest()
    if md5:
        hashes["md5"] = hmd5.hexdigest()
    return hashes


def computeChecksumsFile(fname, sha256=True, sha1=True, md5=True):
    with open(fname, "rb") as flo:
        return computeChecksumsFLO(flo, sha256=sha256, sha1=sha1, md5=md5)
