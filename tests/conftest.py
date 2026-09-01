"""
Pytest configuration and fixtures.
"""
import os
import ssl

# Force offline mode to use cached models (avoids SSL issues with HuggingFace Hub)
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

# Disable SSL verification for tests (avoid HuggingFace SSL issues in corporate environments)
os.environ["CURL_CA_BUNDLE"] = ""
os.environ["REQUESTS_CA_BUNDLE"] = ""
os.environ["SSL_CERT_FILE"] = ""
os.environ["HTTPX_NO_VERIFY_SSL"] = "1"

ssl._create_default_https_context = ssl._create_unverified_context
