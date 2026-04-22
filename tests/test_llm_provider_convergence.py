"""LLM provider 收敛测试。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bananabot.infra import Config, ConfigError
from bananabot.llm import LLMClient, ProviderFactory, ProviderRegistry


class LLMProviderConvergenceTests(unittest.TestCase):
    """冻结 provider 白名单、配置入口和默认行为。"""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.env_path = self.root / ".env"
        self.models_path = self.root / "models.toml"

    def tearDown(self):
        self.tempdir.cleanup()

    def write_env(self, *lines: str) -> None:
        self.env_path.write_text("\n".join(lines), encoding="utf-8")

    def write_models(self, *lines: str) -> None:
        self.models_path.write_text("\n".join(lines), encoding="utf-8")

    def test_provider_registry_is_frozen_to_supported_whitelist(self):
        registry = ProviderRegistry()

        self.assertEqual(registry.list_names(), ["dashscope", "deepseek", "local", "mimo", "minimax"])
        self.assertEqual(registry.get("dashscope").backend, "dashscope")
        self.assertTrue(registry.get("minimax").default_extra_body["reasoning_split"])
        self.assertFalse(registry.get("local").requires_api_key)
        self.assertFalse(registry.get("local").supports_tools)

    def test_provider_factory_exposes_supported_backends(self):
        factory = ProviderFactory()

        self.assertEqual(factory.list_backends(), ["dashscope", "openai_compat"])

    def test_config_builds_registry_from_models_toml_only(self):
        self.write_env(
            "DEFAULT_MODEL=qwen3.6-plus",
            "DASHSCOPE_API_KEY=test-dash",
        )
        self.write_models(
            "[meta]",
            'default_model = "qwen3.6-plus"',
            "",
            "[models.qwen]",
            'alias = "qwen3.6-plus"',
            'provider = "dashscope"',
            'model = "qwen3.6-plus"',
            'description = "Qwen"',
        )

        with patch.dict(os.environ, {}, clear=True), patch(
            "bananabot.infra.config.find_env_file", return_value=self.env_path
        ), patch("bananabot.infra.config.find_models_file", return_value=self.models_path):
            config = Config.from_env()

        profiles = config.model_registry.list_profiles()
        self.assertEqual([profile.alias for profile in profiles], ["qwen3.6-plus"])
        self.assertEqual(profiles[0].base_url, "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.assertEqual(profiles[0].api_key, "test-dash")
        self.assertEqual(config.model_alias, "qwen3.6-plus")

    def test_config_merges_provider_defaults_and_model_overrides(self):
        self.write_env(
            "DEFAULT_MODEL=MiniMax-M2.7",
            "MINIMAX_API_KEY=test-mini",
        )
        self.write_models(
            "[meta]",
            'default_model = "MiniMax-M2.7"',
            "",
            "[models.minimax]",
            'alias = "MiniMax-M2.7"',
            'provider = "minimax"',
            'model = "MiniMax-M2.7"',
            'extra_body = { temperature = 0.2 }',
            'supports_tools = false',
        )

        with patch.dict(os.environ, {}, clear=True), patch(
            "bananabot.infra.config.find_env_file", return_value=self.env_path
        ), patch("bananabot.infra.config.find_models_file", return_value=self.models_path):
            config = Config.from_env()

        profile = config.model_registry.get("MiniMax-M2.7")
        self.assertEqual(profile.extra_body["reasoning_split"], True)
        self.assertEqual(profile.extra_body["temperature"], 0.2)
        self.assertFalse(profile.capabilities.supports_tools)
        self.assertTrue(profile.capabilities.supports_reasoning)

    def test_config_allows_local_model_without_api_key(self):
        self.write_env(
            "DEFAULT_MODEL=gemma-4-e4b-it-4bit",
        )
        self.write_models(
            "[meta]",
            'default_model = "gemma-4-e4b-it-4bit"',
            "",
            "[models.local]",
            'alias = "gemma-4-e4b-it-4bit"',
            'provider = "local"',
            'model = "gemma-4-e4b-it-4bit"',
            'supports_tools = false',
        )

        with patch.dict(os.environ, {}, clear=True), patch(
            "bananabot.infra.config.find_env_file", return_value=self.env_path
        ), patch("bananabot.infra.config.find_models_file", return_value=self.models_path):
            config = Config.from_env()

        profile = config.model_registry.get("gemma-4-e4b-it-4bit")
        self.assertEqual(profile.base_url, "http://127.0.0.1:8000/v1")
        self.assertEqual(profile.api_key, "")
        self.assertFalse(profile.capabilities.supports_tools)

    def test_config_raises_when_default_model_is_skipped_by_missing_key(self):
        self.write_env(
            "DEFAULT_MODEL=deepseek-chat",
        )
        self.write_models(
            "[meta]",
            'default_model = "deepseek-chat"',
            "",
            "[models.deepseek]",
            'alias = "deepseek-chat"',
            'provider = "deepseek"',
            'model = "deepseek-chat"',
            'description = "DeepSeek"',
        )

        with patch.dict(os.environ, {}, clear=True), patch(
            "bananabot.infra.config.find_env_file", return_value=self.env_path
        ), patch("bananabot.infra.config.find_models_file", return_value=self.models_path):
            with self.assertRaises(ConfigError):
                Config.from_env()

    def test_llm_client_requires_configured_model_registry(self):
        self.write_env(
            "DEFAULT_MODEL=qwen3.6-plus",
            "DASHSCOPE_API_KEY=test-dash",
        )
        self.write_models(
            "[meta]",
            'default_model = "qwen3.6-plus"',
            "",
            "[models.qwen]",
            'alias = "qwen3.6-plus"',
            'provider = "dashscope"',
            'model = "qwen3.6-plus"',
        )

        with patch.dict(os.environ, {}, clear=True), patch(
            "bananabot.infra.config.find_env_file", return_value=self.env_path
        ), patch("bananabot.infra.config.find_models_file", return_value=self.models_path):
            config = Config.from_env()

        client = LLMClient(model_registry=config.model_registry, default_model=config.model_alias)
        self.assertEqual(client.get_model_alias(), "qwen3.6-plus")
        self.assertEqual(client.base_url, "https://dashscope.aliyuncs.com/compatible-mode/v1")


if __name__ == "__main__":
    unittest.main()
