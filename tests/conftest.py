"""
Pytest configuration and fixtures.
"""
import os
import ssl

# Disable SSL verification for tests (avoid HuggingFace SSL issues)
os.environ["CURL_CA_BUNDLE"] = ""
os.environ["REQUESTS_CA_BUNDLE"] = ""
ssl._create_default_https_context = ssl._create_unverified_context
