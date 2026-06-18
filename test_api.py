import requests
from crypto_analyser.config import load_config

config = load_config()

api_url = config.api_keys["llm_api_url"]
api_key = config.api_keys["llm_api_key"]

session = requests.Session()

session.headers.update({
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
})

payload = {
    "model": "qwen3-embedding",
    "input": ["This is my first sript test."]
}

resp = session.post(
    f"{api_url}/embeddings",
    json=payload,
    timeout=60,
)

data = resp.json()

print(data)
