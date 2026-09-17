# Ollama iGPU Offload and LLM Refine Model Strategy

On Windows machines with AMD Radeon integrated graphics (APUs such as Ryzen 7 7735U with Radeon 680M), Ollama by default drops the iGPU and falls back to CPU execution. Machine-level variables (`OLLAMA_NUM_GPU=0`, `OLLAMA_NUM_PARALLEL=4`, `OLLAMA_NUM_THREAD=14`) previously forced CPU-only execution with 14 threads and 4 slots, causing thread contention, high thermals, and sluggish generation (~1.1 tokens/s on 12B models) that exceeded HTTP timeouts.

We configured Windows User-level environment variables (`OLLAMA_IGPU_ENABLE=1`, `OLLAMA_NUM_GPU=999`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_NUM_THREAD=8`) to override machine settings, offload 100% of model layers to the Radeon 680M iGPU via Ollama's Vulkan backend, and keep the CPU free. We also standardized on `gemma4:e4b` in `core/refine.py`, retired `translategemma:12b`, disabled thinking overhead (`think: False`), increased the request timeout to 180s, and bounded the inference context to `num_ctx: 2048`.

## Status
Accepted

## Considered Options
1. **CPU Execution with Reduced Threads**: Constrained by mobile APU thermal budgets (15–28W TDP), causing loud fan noise and high CPU temperatures during office use.
2. **Hardcoded 12B Model**: Translation tone is good, but DDR5-4800 memory bandwidth limits generation speed to ~1.1 tokens/sec, taking over a minute per page.
3. **Vulkan iGPU Offload with Gemma 4 E4B (Selected)**: Offloads layers to Radeon 680M via Vulkan, reduces memory footprint, keeps the laptop responsive, and runs 10x faster with natural manga dialogue.

## Consequences
- The user restarts Ollama once (closing from the Windows system tray and reopening) for User environment variables to take effect.
- `gemma4:e4b` is the exclusive model for manga refinement, freeing 8.1 GB of disk space from `translategemma:12b`.
- Memory consumption per model is significantly reduced by eliminating unnecessary parallel slots and restricting context size to 2048 tokens.
