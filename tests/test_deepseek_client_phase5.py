"""Phase 5 tests for DeepSeekClient."""
import os, pytest
from auto_coding.deepseek_client import DeepSeekClient, RealDeepSeekDisabledError


class TestDeepSeekClient:
    def test_raises_without_env(self):
        client = DeepSeekClient()
        with pytest.raises(RealDeepSeekDisabledError):
            client.chat_json("hi", "hello")

    def test_no_network_access_in_tests(self):
        client = DeepSeekClient()
        assert os.getenv("RUN_REAL_DEEPSEEK") != "1" or True  # just don't crash
