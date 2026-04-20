# Chaz Agent Portal — Design System

## "The Thinking Machine"

---

## Color Palette

| Token | Hex | Description |
|-------|-----|-------------|
| `--bg` | `#0f0e0d` | Warm charcoal — primary background (NOT pure black) |
| `--surface` | `#1c1816` | Slightly lighter warm dark — card/section backgrounds |
| `--primary` | `#b5694a` | Terracotta/rust — primary accent, CTAs, highlights |
| `--secondary` | `#e8d5c4` | Warm cream — elegant contrast, borders, icons |
| `--text` | `#f5f0eb` | Warm off-white — primary text |
| `--muted` | `#8a7f75` | Warm gray — secondary text, captions |
| `--divider` | `rgba(232,213,196,0.12)` | Subtle warm border/divider |

---

## Typography

### Google Fonts Import
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500;600;700&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

### Type Scale

| Role | Font | Weight | Size | Line Height |
|------|------|--------|------|-------------|
| Hero Title | Playfair Display | 400 | 72–96px | 1.1 |
| H1 | Playfair Display | 500 | 48–64px | 1.15 |
| H2 | Playfair Display | 400 | 36–48px | 1.2 |
| H3 | Playfair Display | 400 | 24–32px | 1.3 |
| Body | Inter | 400 | 16–18px | 1.6 |
| UI/Labels | Inter | 500 | 13–14px | 1.4 |
| Mono/Code | JetBrains Mono | 400 | 13–14px | 1.5 |

---

## Gradient Text Fade (Signature Move)

The hero title features a gradient fade from solid warm cream → transparent.

### CSS Recipe
```css
.hero-title {
  font-family: 'Playfair Display', serif;
  font-size: clamp(48px, 8vw, 96px);
  font-weight: 400;
  background: linear-gradient(
    to bottom,
    #f5f0eb 0%,
    #f5f0eb 60%,
    rgba(245, 240, 235, 0.4) 80%,
    transparent 100%
  );
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
```

### Alternative: Multi-stop for deeper fade
```css
background: linear-gradient(
  to bottom,
  #f5f0eb 0%,
  #e8d5c4 40%,
  rgba(232, 213, 196, 0.15) 70%,
  transparent 100%
);
```

---

## Animation Principles

### Scroll Reveal
Elements fade + translate on scroll into view.

```css
.reveal {
  opacity: 0;
  transform: translateY(24px);
  transition: opacity 0.7s ease, transform 0.7s ease;
}

.reveal.visible {
  opacity: 1;
  transform: translateY(0);
}
```

### Stagger Timing
For lists/grids of items — delay each child by 80ms.

```css
.reveal-stagger > * {
  transition-delay: calc(var(--i, 0) * 80ms);
}
```

### Easing
- **Default:** `cubic-bezier(0.25, 0.1, 0.25, 1)` — smooth, not bouncy
- **Entrance:** `cubic-bezier(0.16, 1, 0.3, 1)` — slight overshoot for energy
- **Exit:** `cubic-bezier(0.7, 0, 0.84, 0)` — quick departure

### Duration
- Micro-interactions: 150–250ms
- Section transitions: 500–700ms
- Page-level reveals: 800–1000ms

### Hover States
```css
/* Subtle lift + glow on cards */
.card:hover {
  transform: translateY(-4px);
  box-shadow: 0 20px 40px rgba(0,0,0,0.3), 0 0 0 1px rgba(181,105,74,0.2);
  transition: all 0.3s cubic-bezier(0.25, 0.1, 0.25, 1);
}

/* Icon hover — gentle scale */
.icon:hover {
  transform: scale(1.08);
  transition: transform 0.2s ease;
}
```

---

## Spacing Rhythm

Generous whitespace. Sections should breathe.

| Token | Value | Use |
|-------|-------|-----|
| `--space-xs` | 8px | Tight internal spacing |
| `--space-sm` | 16px | Component padding |
| `--space-md` | 32px | Section internal gaps |
| `--space-lg` | 64px | Section vertical padding |
| `--space-xl` | 128px | Hero / major section breaks |
| `--space-2xl` | 192px | Maximum breathing room |

### Section Vertical Rhythm
- Hero: `--space-2xl` top padding
- Content sections: `--space-xl` top, `--space-lg` bottom
- Cards/grid sections: `--space-lg` padding throughout
- Footer: `--space-lg` padding

---

## Layout

### Max Width
- Content: 1200px max-width, centered
- Text blocks: 720px max-width (for readability)
- Hero: Full-width or 1400px max

### Grid
- 12-column grid with 24px gutters
- Cards: 3-column on desktop, 2 on tablet, 1 on mobile

### Breakpoints
```css
--bp-mobile: 640px;
--bp-tablet: 1024px;
--bp-desktop: 1280px;
```

---

## Borders & Dividers

```css
--border: 1px solid rgba(232, 213, 196, 0.12);
--border-strong: 1px solid rgba(232, 213, 196, 0.24);
--radius-sm: 4px;
--radius-md: 8px;
--radius-lg: 16px;
--radius-full: 9999px;
```

---

## Shadows

```css
--shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.2);
--shadow-md: 0 8px 24px rgba(0, 0, 0, 0.3);
--shadow-lg: 0 16px 48px rgba(0, 0, 0, 0.4);
--shadow-glow: 0 0 40px rgba(181, 105, 74, 0.15); /* terracotta glow */
```

---

## SVG Assets

All SVGs in `/docs/assets/` use this consistent styling:
- viewBox-based sizing (no fixed width/height on inline)
- Stroke-based illustration (no fills except accents)
- 1–1.5px stroke weight
- `stroke-linecap: round`, `stroke-linejoin: round`
- Warm palette: `#b5694a`, `#e8d5c4`, `#8a7f75`
- No blue, green, or cyan

---

## CSS Variables Template

```css
:root {
  /* Colors */
  --bg: #0f0e0d;
  --surface: #1c1816;
  --primary: #b5694a;
  --secondary: #e8d5c4;
  --text: #f5f0eb;
  --muted: #8a7f75;
  --divider: rgba(232, 213, 196, 0.12);

  /* Typography */
  --font-serif: 'Playfair Display', Georgia, serif;
  --font-sans: 'Inter', -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;

  /* Spacing */
  --space-xs: 8px;
  --space-sm: 16px;
  --space-md: 32px;
  --space-lg: 64px;
  --space-xl: 128px;
  --space-2xl: 192px;

  /* Radii */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 16px;
  --radius-full: 9999px;

  /* Shadows */
  --shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.2);
  --shadow-md: 0 8px 24px rgba(0, 0, 0, 0.3);
  --shadow-lg: 0 16px 48px rgba(0, 0, 0, 0.4);
  --shadow-glow: 0 0 40px rgba(181, 105, 74, 0.15);
}
```

---

## Motion Summary

| Effect | Duration | Easing | Trigger |
|--------|----------|--------|---------|
| Fade up on scroll | 700ms | `cubic-bezier(0.16, 1, 0.3, 1)` | Intersection Observer |
| Card hover lift | 300ms | `cubic-bezier(0.25, 0.1, 0.25, 1)` | `:hover` |
| Button press | 150ms | `ease-out` | `:active` |
| Gradient text | 800ms | `ease` | Page load (delay 200ms) |
| Stagger children | 80ms | `ease` | Per item index |
