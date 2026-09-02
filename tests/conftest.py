"""
Pytest configuration and fixtures.
"""
import os
import ssl

from dotenv import load_dotenv

load_dotenv()  # so EMBEDDINGS_OFFLINE_MODE in a local .env reaches os.environ

# Mirrors app/embeddings.py: only force offline/SSL-bypass mode when explicitly
# opted in via EMBEDDINGS_OFFLINE_MODE (corporate networks with a pre-cached model).
# CI runners have no cache and normal internet access, so this must stay off there.
if os.environ.get("EMBEDDINGS_OFFLINE_MODE", "").lower() in ("1", "true", "yes"):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["CURL_CA_BUNDLE"] = ""
    os.environ["REQUESTS_CA_BUNDLE"] = ""
    os.environ["SSL_CERT_FILE"] = ""
    os.environ["HTTPX_NO_VERIFY_SSL"] = "1"
    ssl._create_default_https_context = ssl._create_unverified_context
