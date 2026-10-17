from stylesense.integrations.llm.groq_provider import GROQ_BASE_URL, GroqProvider


def test_reasoning_models_think_briefly_and_others_get_no_extra_options() -> None:
    groq = GroqProvider("gsk-test")

    assert groq._extra_options("openai/gpt-oss-20b") == {"reasoning_effort": "low"}
    assert groq._extra_options("qwen/qwen3.8-27b") == {"reasoning_effort": "low"}
    assert groq._extra_options("llama-3.3-70b-versatile") == {}
    assert str(groq._client.base_url).rstrip("/") == GROQ_BASE_URL


def test_groq_never_sends_the_openai_only_prompt_cache_key() -> None:
    assert GroqProvider.supports_prompt_cache_key is False
