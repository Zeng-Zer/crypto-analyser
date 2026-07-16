from crypto_analyser._paths import asset_path
from crypto_analyser.classification.episodes import PromptTemplate
from crypto_analyser.llm_client import LLMClient


def test_packaged_assets_load():

    assert PromptTemplate.load().system
    assert LLMClient._load_schema()["title"] == "CryptoAnomalyClassification"
    assert asset_path("schema.sql").is_file()
