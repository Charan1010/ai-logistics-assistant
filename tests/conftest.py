"""
Pytest configuration and fixtures.
"""
import os
import ssl

# Disable SSL verification for tests (avoid HuggingFace SSL issues in corporate environments)
os.environ["CURL_CA_BUNDLE"] = ""
os.environ["REQUESTS_CA_BUNDLE"] = ""
os.environ["SSL_CERT_FILE"] = ""
os.environ["HTTPX_NO_VERIFY_SSL"] = "1"

ssl._create_default_https_context = ssl._create_unverified_context

# Patch httpx Client to disable SSL verification
import httpx
original_client_init = httpx.Client.__init__

def patched_client_init(self, *args, **kwargs):
    kwargs['verify'] = False
    original_client_init(self, *args, **kwargs)

httpx.Client.__init__ = patched_client_init
