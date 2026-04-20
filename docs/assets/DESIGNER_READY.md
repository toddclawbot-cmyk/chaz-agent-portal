# Designer → Coder Coordination

## "The Thinking Machine" — Chaz Agent Portal

---

## Design Direction Summary

**Aesthetic:** Understated luxury. Editorial. Warm earthy tones. Massive negative space. Center-aligned. Inspired by Max Mara's digital presence — nothing corporate, nothing startup-y.

**Mood:** A thinking machine that reasons elegantly, not a flashy AI demo.

---

## Assets Created

### Illustrations (SVG)
| File | Description | Dimensions |
|------|-------------|------------|
| `hero-illustration.svg` | Central agent node with curved lines to Groq (circle), Databricks (hexagon), Salesforce (rectangle with cloud) | 800×500 |
| `reasoning-chain.svg` | 6-node vertical flow with numbered markers (01–05) and curved connectors | 200×480 |
| `data-systems.svg` | Horizontal view: Groq/Databricks/Salesforce connected to central agent | 600×200 |
| `flow-timeline.svg` | Ask → Think → Act with gradient connecting line | 600×160 |

### Icons (SVG, 48×48, 1.5px stroke)
| File | Purpose |
|------|---------|
| `icon-language.svg` | Natural Language — speech bubble + sparkle |
| `icon-database.svg` | Databricks — elegant cylinder |
| `icon-salesforce.svg` | Salesforce — simple cloud outline |
| `icon-zap.svg` | Real-time Action — lightning bolt |
| `icon-layers.svg` | Multi-system — stacked layers with dots |
| `icon-trace.svg` | Visible Reasoning Trace — radiating node |

### Brand
| File | Description |
|------|-------------|
| `favicon.svg` | CA monogram in agent node, terracotta on transparent |
| `DESIGN.md` | Full design system — colors, typography, animations, spacing |

---

## Key Design Decisions

### Color Usage
- Background: `#0f0e0d` (never pure black)
- Primary accent: `#b5694a` (terracotta) — use for CTAs, key highlights
- Secondary: `#e8d5c4` (warm cream) — use for icons, borders, text contrast
- Text: `#f5f0eb` (warm off-white)
- Muted: `#8a7f75` (warm gray) — captions, secondary text

### Typography
- **Headlines:** Playfair Display (serif) — editorial luxury
- **Body/UI:** Inter (clean sans-serif)
- **Code/mono:** JetBrains Mono
- **Hero title:** MUST use gradient fade (solid → transparent, see DESIGN.md)

### SVG Styling Rules
- All illustrations: stroke-based, no fills (except accent dots)
- 1–1.5px stroke weight
- Warm palette only — NO blue, green, or cyan
- `stroke-linecap: round`, `stroke-linejoin: round` on all paths
- viewBox-based sizing — no fixed width/height attributes

### Animation Direction
- Scroll reveals: fade + subtle Y translation (24px)
- Easing: `cubic-bezier(0.16, 1, 0.3, 1)` for entrance
- Stagger: 80ms between items
- Hover: subtle lift (-4px Y) + terracotta glow on cards
- Hero text: gradient fade on load

### Spacing Philosophy
- **Generous.** Sections should breathe.
- Hero: `--space-2xl` top padding (192px)
- Content sections: `--space-xl` top (128px)
- Cards: `--space-lg` internal padding (64px)

---

## Wiring Notes for Coder

1. **Hero SVG:** Use as-is as background element, position behind text
2. **Section illustrations:** Place inline in relevant sections
3. **Icons:** Use as `<img>` or inline SVG in capability cards
4. **Gradient text:** Copy CSS from DESIGN.md hero-title example exactly
5. **All SVGs are inline-friendly** — no external dependencies

---

## What I (Designer) Need From You (Coder)

- Confirm all SVGs render correctly at various viewport sizes
- The hero illustration should scale gracefully (it's 800×500 aspect)
- If any SVG looks off at different sizes, flag it and I'll adjust the viewBox
- The terracotta glow shadow (`--shadow-glow`) should be used sparingly — hero and key CTAs only

---

*Design direction locked. Ready to build.*
