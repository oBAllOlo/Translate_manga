# 0007: Pluggable Refine Provider with OpenRouter Nemotron Reasoning and Local Ollama Fallback

We decided to introduce a pluggable RefineProvider architecture supporting both local offline inference (Ollama with gemma4:e4b) and cloud-based reasoning models via OpenRouter (nvidia/nemotron-3-ultra-550b-a55b:free), capturing reasoning details and providing automatic rate-limit backoff with local fallback.

## Status
Accepted

## Decisions

1. **Pluggable RefineProvider Abstraction**: Decouple refinement logic from a single backend into a provider interface (`RefineProvider`), offering `OllamaProvider` (default offline) and `OpenRouterProvider` (cloud reasoning).
2. **Reasoning Details Persistence**: Support models returning `reasoning_details`. Persist internal thought chains alongside refined dialogue in `llm_refined.json` for auditing in the Reader UI.
3. **Preserved Multi-Turn Continuation**: Enable interactive page touch-up and re-refining in the Reader by returning prior `reasoning_details` in subsequent conversation turns to maintain tone and context.
4. **Per-Page Dynamic Fallback**: Run batch page requests sequentially with rate-limit backoff. If OpenRouter fails on a page after retries, fall back dynamically for that page to local Ollama (`gemma4:e4b`), recording the exact model used per page.
5. **Interactive Streaming via SSE**: Support Server-Sent Events (`stream: true`) for single-page interactive refinement in the Reader UI, streaming reasoning tokens and text incrementally.
6. **Additive Non-Breaking Schema**: Extend `llm_refined.json` with additive fields (`provider`, `reasoning_details`, `history`) preserving full backwards compatibility with existing chapter metadata.
7. **Reasoning-Aware Prompting**: Instruct 550B reasoning models to analyze character relationships, tone/slang, and bubble length constraints during the thinking phase prior to emitting Thai dialogue.
8. **Collapsible Reasoning UI**: Render reasoning details in an accordion card ("💭 วิเคราะห์บทสนทนา (Reasoning Process)") in the Reader comparison panel, collapsed by default to save screen space while keeping thought chains accessible.
9. **OpenRouter Attribution Headers**: Transmit `HTTP-Referer: https://github.com/oBAllOlo/Translate_manga` and `X-Title: Manga Translate` in API requests according to OpenRouter standards.
10. **Configuration Priority**: Resolve OpenRouter API keys and provider selection from Web UI / Database settings first, falling back to environment variables (`OPENROUTER_API_KEY`).

## Rationale

While local Ollama preserves 100% offline privacy and zero API costs, high-parameter reasoning models like Nemotron 3 Ultra 550B provide superior Thai dialogue nuance, idiomatic flow, and character-specific voice. By adopting a dual-provider architecture, users retain offline self-sufficiency while optionally unlocking state-of-the-art cloud reasoning.


