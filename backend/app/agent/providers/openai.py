from app.agent.providers.openai_compatible import OpenAICompatibleProvider
from app.agent.providers.registry import register_provider


@register_provider("openai")
class OpenAIProvider(OpenAICompatibleProvider):
    """Plain OpenAI. Nothing special, it just gets its own name in the UI."""
