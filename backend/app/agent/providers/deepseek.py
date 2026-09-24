from app.agent.providers.openai_compatible import OpenAICompatibleProvider
from app.agent.providers.registry import register_provider


@register_provider("deepseek")
class DeepSeekProvider(OpenAICompatibleProvider):
    """DeepSeek's API is OpenAI-shaped. The one wrinkle: deepseek-reasoner
    rejects tool definitions, so tools get dropped for that model."""

    @property
    def supports_tools(self) -> bool:  # type: ignore[override]
        return "reasoner" not in self.model
