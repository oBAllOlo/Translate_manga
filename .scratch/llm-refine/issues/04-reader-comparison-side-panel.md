# Ticket 04: Reader Comparison Side Panel

## Description
Provide a collapsible side panel in the Reader UI allowing readers to compare original Google Lens translation against the AI-refined translation and trigger per-page refinement.

## Requirements
- Toggle button in reader toolbar (HUD) with Sparkles icon.
- Side panel displaying:
  - Current page number.
  - Original Google Lens Thai text.
  - Refined Thai text (TranslateGemma 12B).
  - Status badge (Refined vs Not Refined).
  - Single-page "Refine" / "Re-refine" button with loading indicator.
- Automatically synchronizes with current page in reader.
