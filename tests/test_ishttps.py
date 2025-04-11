import pytest
import sonormal

https_tests = [
    [{}, False],
    [
        [
            {
                "@type": ["https://schema.org/Dataset"],
                "https://schema.org/creator": [
                    {
                        "@type": ["https://schema.org/Person"],
                        "https://schema.org/name": [{"@value": "creator_02"}],
                    },
                    {
                        "@type": ["https://schema.org/Person"],
                        "https://schema.org/name": [{"@value": "creator_01"}],
                    },
                ],
                "https://schema.org/description": [
                    {
                        "@value": "No remote context, vocab https://schema.org/, creator 02, 01"
                    }
                ],
            }
        ],
        True,
    ],
    [
        [
            {
                "@type": ["http://schema.org/Dataset"],
                "http://schema.org/creator": [
                    {
                        "@type": ["http://schema.org/Person"],
                        "http://schema.org/name": [{"@value": "creator_02"}],
                    },
                    {
                        "@type": ["http://schema.org/Person"],
                        "http://schema.org/name": [{"@value": "creator_01"}],
                    },
                ],
                "http://schema.org/description": [
                    {
                        "@value": "No remote context, vocab https://schema.org/, creator 02, 01"
                    }
                ],
            }
        ],
        False,
    ],
]


@pytest.mark.parametrize("exp_doc, expected", https_tests)
def test_isHttpsSchemaOrg(exp_doc, expected):
    assert sonormal.isHttpsSchemaOrg(exp_doc) == expected
