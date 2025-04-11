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
    cache = sonormal.DOCUMENT_CACHE
    options = {
        "documentLoader": sonormal.localRequestsDocumentLoader(sonormal.SO_CONTEXT, document_cache=cache)
    }
    edoc = pyld.jsonld.expand(tdoc, options)
    v = edoc[0].get("http://schema.org/name", [{}])[0].get("@value")
    assert v == "test value"


def test_remote(soContext):
    doc = {"@context": "https://schema.org/", "name": "test value"}
    tdoc = sonormal.switchToHttpSchemaOrg(doc)
    assert tdoc.get("@context") in sonormal.SCHEMA_ORG_CONTEXT_URLS
    cache = sonormal.DOCUMENT_CACHE
    options = {
        "documentLoader": sonormal.localRequestsDocumentLoader(sonormal.SO_CONTEXT, document_cache=cache)
    }
    edoc = pyld.jsonld.expand(tdoc, options)
    v = edoc[0].get("http://schema.org/name", [{}])[0].get("@value")
    assert v == "test value"


def test_prefix(soContext):
    doc = {"@context": {"so": "https://schema.org/"}, "so:name": "test value"}
    tdoc = sonormal.switchToHttpSchemaOrg(doc)
    assert tdoc.get("@context") in sonormal.SCHEMA_ORG_CONTEXT_URLS
    cache = sonormal.DOCUMENT_CACHE
    options = {
        "documentLoader": sonormal.localRequestsDocumentLoader(sonormal.SO_CONTEXT, document_cache=cache)
    }
    edoc = pyld.jsonld.expand(tdoc, options)
    v = edoc[0].get("http://schema.org/name", [{}])[0].get("@value")
    assert v == "test value"


def test_base(soContext):
    doc = {
        "@context": {"so": "https://schema.org/"},
        "@id": "test_base",
        "so:name": "test value",
    }
    options = {"base": "https://example.xyz/test/"}
    tdoc = sonormal.switchToHttpSchemaOrg(doc, options=options)
    assert tdoc.get("@context") in sonormal.SCHEMA_ORG_CONTEXT_URLS
    cache = sonormal.DOCUMENT_CACHE
    options = {
        "documentLoader": sonormal.localRequestsDocumentLoader(sonormal.SO_CONTEXT, document_cache=cache)
    }
    edoc = pyld.jsonld.expand(tdoc, options)
    v = edoc[0].get("http://schema.org/name", [{}])[0].get("@value")
    assert v == "test value"
    vb = edoc[0].get("@id", None)
    assert vb == "https://example.xyz/test/test_base"


dryad_test_doc_1 = [{'@context': 'http://schema.org',
             '@id': 'https://doi.org/10.5061/dryad.cv270',
             '@type': 'Dataset',
             'citation': 'http://doi.org/10.1111/mec.14780',
             'creator': [{'@type': 'Person',
                          'affiliation': {'@type': 'Organization',
                                          'name': 'Indiana University '
                                                  'Bloomington',
                                          'sameAs': 'https://ror.org/02k40bc56'},
                          'familyName': 'Wu',
                          'givenName': 'Meng',
                          'name': 'Meng Wu'},
                         {'@type': 'Person',
                          'affiliation': {'@type': 'Organization',
                                          'name': 'University of Vermont',
                                          'sameAs': 'https://ror.org/0155zta11'},
                          'familyName': 'Kostyun',
                          'givenName': 'Jamie L.',
                          'name': 'Jamie L. Kostyun'},
                         {'@type': 'Person',
                          'affiliation': {'@type': 'Organization',
                                          'name': 'Indiana University '
                                                  'Bloomington',
                                          'sameAs': 'https://ror.org/02k40bc56'},
                          'familyName': 'Hahn',
                          'givenName': 'Matthew W.',
                          'name': 'Matthew W. Hahn'},
                         {'@type': 'Person',
                          'affiliation': {'@type': 'Organization',
                                          'name': 'Indiana University '
                                                  'Bloomington',
                                          'sameAs': 'https://ror.org/02k40bc56'},
                          'familyName': 'Moyle',
                          'givenName': 'Leonie C.',
                          'name': 'Leonie C. Moyle'}],
             'description': ['Phylogenetic analyses of trait evolution can '
                             'provide insight into the evolutionary processes '
                             'that initiate and drive phenotypic '
                             'diversification. However, recent phylogenomic '
                             'studies have revealed extensive gene '
                             'tree-species tree discordance, which can lead to '
                             'incorrect inferences of trait evolution if only '
                             'a single species tree is used for analysis. This '
                             'phenomenonâ\x80\x94dubbed '
                             'â\x80\x9chemiplasyâ\x80\x9dâ\x80\x94is '
                             'particularly important to consider during '
                             'analyses of character evolution in rapidly '
                             'radiating groups, where discordance is '
                             'widespread. Here we generate whole-transcriptome '
                             'data for a phylogenetic analysis of 14 species '
                             'in the plant genus Jaltomata (the sister clade '
                             'to Solanum), which has experienced rapid, recent '
                             'trait evolution, including in fruit and nectar '
                             'color, and flower size and shape. Consistent '
                             'with other radiations, we find evidence for '
                             'rampant gene tree discordance due to incomplete '
                             'lineage sorting (ILS) and to introgression '
                             'events among the well-supported subclades. Since '
                             'both ILS and introgression increase the '
                             'probability of hemiplasy, we perform several '
                             'analyses that take discordance into account '
                             'while identifying genes that might contribute to '
                             'phenotypic evolution. Despite discordance, the '
                             'history of fruit color evolution in Jaltomata '
                             'can be inferred with high confidence, and we '
                             'find evidence of de novo adaptive evolution at '
                             'individual genes associated with fruit color '
                             'variation. In contrast, hemiplasy appears to '
                             'strongly affect inferences about floral '
                             'character transitions in Jaltomata, and we '
                             'identify candidate loci that could arise either '
                             'from multiple lineage-specific substitutions or '
                             'standing ancestral polymorphisms. Our analysis '
                             'provides a generalizable example of how to '
                             'manage discordance when identifying loci '
                             'associated with trait evolution in a radiating '
                             'lineage.',
                             '<div class="o-metadata__file-usage-entry"><h4 '
                             'class="o-heading__level3-file-title">Jalt_noSolyc_codon.tar</h4><div '
                             'class="o-metadata__file-description">The mvf '
                             'file used for PhyloGWAS analysis on Jaltomata '
                             'lineages. Tomato (the outgroup) sequences were '
                             'not included in this dataset.</div><div '
                             'class="o-metadata__file-name"></div></div><div '
                             'class="o-metadata__file-usage-entry"><h4 '
                             'class="o-heading__level3-file-title">phylogeny_aln.tar</h4><div '
                             'class="o-metadata__file-description">The gene '
                             'sequence alignments (codon-forced; FASTA format) '
                             'used for phylogeny reconstruction, introgression '
                             'and genetic distance analyses.</div><div '
                             'class="o-metadata__file-name"></div></div><div '
                             'class="o-metadata__file-usage-entry"><h4 '
                             'class="o-heading__level3-file-title">paml_aln_noCap.tar</h4><div '
                             'class="o-metadata__file-description">The gene '
                             'sequence alignments (codon-forced; FASTA format) '
                             'used for PAML branch-site and clade analyses '
                             'within Jaltomata lineages.</div><div '
                             'class="o-metadata__file-name"></div></div><div '
                             'class="o-metadata__file-usage-entry"><h4 '
                             'class="o-heading__level3-file-title">paml_aln_wtCap.tar</h4><div '
                             'class="o-metadata__file-description">The gene '
                             'sequence alignments (codon-forced; FASTA format) '
                             'used for PAML branch-site on the ancestral '
                             'branch of Jaltomata lineages with Capsicum as '
                             'outgroup.</div><div '
                             'class="o-metadata__file-name"></div></div><div '
                             'class="o-metadata__file-usage-entry"><h4 '
                             'class="o-heading__level3-file-title">variants_v2.mvf.tar</h4><div '
                             'class="o-metadata__file-description">The mvf '
                             'file used for estimating heterozygous and shared '
                             'polymorphism sites among Jaltomata lineages. To '
                             'generate this dataset, reads from each RNA-seq '
                             'library were mapped to the tomato reference '
                             'genome and then variants were called.</div><div '
                             'class="o-metadata__file-name"></div></div>'],
             'distribution': {'@type': 'DataDownload',
                              'contentUrl': 'http://datadryad.org/api/v2/datasets/doi%253A10.5061%252Fdryad.cv270/download',
                              'encodingFormat': 'application/zip'},
             'identifier': 'https://doi.org/10.5061/dryad.cv270',
             'isAccessibleForFree': True,
             'keywords': ['hemiplasy',
                          'rapid radiation',
                          'Solanum',
                          'covergence',
                          'Jaltomata'],
             'license': {'@type': 'CreativeWork',
                         'license': 'https://creativecommons.org/publicdomain/zero/1.0/',
                         'name': 'CC0 1.0 Universal (CC0 1.0) Public Domain '
                                 'Dedication'},
             'name': 'Dissecting the basis of novel trait evolution in a '
                     'radiation with widespread phylogenetic discordance',
             'provider': {'@id': 'https://datadryad.org'},
             'publisher': {'@id': 'https://datadryad.org',
                           '@type': 'Organization',
                           'legalName': 'Dryad Digital Repository',
                           'name': 'Dryad',
                           'url': 'https://datadryad.org'},
             'spatialCoverage': [],
             'temporalCoverage': ['2018', '2018-06-27T13:22:18Z'],
             'url': 'http://datadryad.org/stash/dataset/doi%253A10.5061%252Fdryad.cv270',
             'version': 1}]


def test_dryad(soContext):
    doc = dryad_test_doc_1
    tdoc = sonormal.switchToHttpSchemaOrg(doc)
    print(json.dumps(tdoc, indent=2))
    assert tdoc.get("@context") == "https://schema.org/"
    cache = sonormal.DOCUMENT_CACHE
    options = {
        "documentLoader": sonormal.localRequestsDocumentLoader(sonormal.SOL_CONTEXT, document_cache=cache)
    }
    edoc = pyld.jsonld.expand(tdoc, options)
    v = edoc[0].get("http://schema.org/name", [{}])[0].get("@value")
    assert v == "Dissecting the basis of novel trait evolution in a radiation with widespread phylogenetic discordance"
