import json

from crypto_analyser.rag.archive_loader import clean_value, parse_file


def test_clean_value_normalizes_null_and_cdata():
    assert clean_value("NULL") is None
    assert clean_value(" <![CDATA[headline]]> ") == "headline"


def test_parse_file_normalizes_archive_article(tmp_path):
    path = tmp_path / "day.json"
    path.write_text(
        json.dumps(
            {
                "date": "2022-05-07",
                "articles": [
                    {
                        "title": "Terra update",
                        "link": "https://example.test/terra",
                        "description": "NULL",
                        "pubDate": "2022-05-07T12:00:00Z",
                        "source": "Historical",
                        "category": "general",
                        "currencies": ["LUNA", "UST"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert parse_file(path) == [
        {
            "title": "Terra update",
            "description": None,
            "link": "https://example.test/terra",
            "pub_date": "2022-05-07T12:00:00Z",
            "source": "Historical",
            "category": "general",
            "tickers": ["LUNA", "UST"],
            "sentiment": None,
        }
    ]
