"""
TradeVision AI — AI provider implementations package.

Available providers:
    gemini    — Google Gemini (active, Phase 0: auth only)
    openai    — OpenAI GPT      (stub, Phase 0)
    claude    — Anthropic Claude (stub, Phase 0)
    ollama    — Ollama local LLM (stub, Phase 0)
    deepseek  — DeepSeek Chat   (active, Phase 0: auth only)

Import via the factory, not directly::

    from core.ai.provider_factory import AIProviderFactory
    provider = AIProviderFactory.get_provider()
"""
