# Ticket 05: Domain Docs & ADR

## Description
Document the architectural decision and domain terminology for LLM translation refinement.

## Requirements
- Update `CONTEXT.md` with:
  - LLM Refine
  - Refined Text
- Create `docs/adr/0005-llm-refine-with-ollama.md` detailing:
  - Context and Problem
  - Decision: Local LLM (Ollama TranslateGemma 12B), sequential processing, text-only storage in `llm_refined.json`
  - Status and Consequences
