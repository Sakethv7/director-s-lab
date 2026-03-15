# Design System

All styles in `frontend/src/index.css` using CSS custom properties. No Tailwind, no CSS-in-JS.

## Colour Palette

| Variable | Value | Use |
|---|---|---|
| `--bg-base` | `#0d0d0d` | Page background |
| `--bg-panel` | `#1a1a1a` | Cards / panels |
| `--bg-input` | `#111` | Input backgrounds |
| `--gold` | `#c9a84c` | Primary accent, logo, highlights |
| `--border` | `rgba(255,255,255,0.08)` | Subtle borders |
| `--text-primary` | `#f0e6d3` | Main text |
| `--text-secondary` | `#a09080` | Secondary text |
| `--text-muted` | `#555` | Labels, hints |
| `--tension-color` | `#e63946` | Beat map tension bar |
| `--longing-color` | `#9b59b6` | Beat map longing bar |
| `--resolve-color` | `#2ecc71` | Beat map resolve bar |

## Typography

| Variable | Value | Use |
|---|---|---|
| `--font-serif` | Georgia, serif | Body, scene text |
| `--font-mono` | Courier New, monospace | Labels, badges, panel IDs |

## Film Grain

Applied via `body::before` fixed SVG noise filter at z-index 9999, pointer-events none. Pure CSS — no image assets.

## Component Patterns

- **`fade-in`** — opacity 0→1 animation on mount
- **`spinner`** — CSS keyframe rotating border element
- **`beat-section`** — card layout for each production beat
- **`hero-frame`** — large featured panel at the top of the scene view
- **`.export-btn--obsidian`** — purple hover for Obsidian export
- **`.export-btn--notebooklm`** — blue hover for NotebookLM export
- **`.export-btn--copied`** — green flash on successful clipboard copy
