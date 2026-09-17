# 0008: Standardize LLM Refine Exclusively on OpenRouter Nemotron

We decided to retire local Ollama support entirely and standardize on cloud-based OpenRouter (`nvidia/nemotron-3-ultra-550b-a55b:free`) as the sole, primary LLM Refine engine for manga dialogue polishing.

## Status
Accepted (Supersedes ADR 0001, ADR 0005, and amends ADR 0007)

## Decisions

1. **Retire Local Ollama Dependencies**: Remove `OllamaProvider`, `check_ollama_health`, and local Ollama fallback logic. Eliminate all `OLLAMA_*` environment variables and settings.
2. **Standardize on OpenRouter as Primary Refine Engine**: Set OpenRouter (`nvidia/nemotron-3-ultra-550b-a55b:free`) as the default and only refine engine, configured via `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, and `OPENROUTER_BASE_URL`.
3. **Reasoning-First Polishing**: Retain step-by-step reasoning tokens (`reasoning: {"enabled": True}`) to maintain superior character voice, manga idiom nuances, and dialogue flow.
4. **SSE Streaming by Default**: All single-page interactive refinement requests stream reasoning thoughts and final translated dialogue in real time via Server-Sent Events.
5. **Simplified Reader & Library UI**: Remove the Cloud/Local toggle from the Reader UI. Provide a clean OpenRouter Nemotron indicator with an API key settings modal, updating batch and single-chapter action titles to OpenRouter AI.
6. **Robust Rate-Limit Handling**: Maintain exponential backoff retry (up to 3 attempts) for OpenRouter 429 responses directly within the batch pipeline.
7. **Storage Backward Compatibility**: Preserve existing `llm_refined.json` structures, allowing previously refined chapters to remain readable without migration.

## Rationale

Operating local 12B/4B models on consumer hardware (such as APU iGPUs) imposed high system thermals, required manual Vulkan driver tuning, and yielded translations that lagged behind 500B+ parameter reasoning models in Thai dialogue naturalness. Retiring Ollama drastically simplifies the code architecture, removes fragile health-check dependencies, and delivers high-tier translation quality directly via OpenRouter's free tier.
