# 0004: Decoupled Cleaning and Typesetting Pipeline

We decided to decouple text translation from page rendering by moving away from Google Lens's pre-rendered composite images (`imageUrl`). Instead, the pipeline uses Google Lens primarily for OCR and Thai text translation, while performing Cleaning (bubble inpainting and color-matching) and Typesetting (local font rendering and text layout) locally, backed by an interactive Touch-up tool in the Reader UI.

## Decisions
1. **Cleaning Strategy**: Use **Diff Masking** (comparing Original vs Lens image) to locate text regions, dilated to capture ghost text and font borders, followed by OpenCV-based **Bubble Inpainter** that samples neighbor bubble tones to eliminate harsh white rectangular patches.
2. **Typesetting & Typography**: Render Thai text locally using bundled Google Fonts (e.g. *Prompt* / *Sarabun*) with PyThaiNLP word segmentation to prevent overlapping vowels, awkward line breaks, or misplaced text.
3. **Interactive Touch-up**: Provide an in-reader canvas touch-up tool allowing readers to click to edit translations or brush away any remaining artifacts without leaving the reading flow.

## Rationale
This prevents dirty cleaning residue (ghost text) and rectangular white patch artifacts on gradient or textured speech bubbles, allows proper Thai typography and line-wrapping, and empowers users to quickly touch up edge-case panels directly from the browser.
