# OpenClay — Design System Rules

All UI work on this project must follow these rules. No exceptions.
Canonical source of truth: `openclay-landing.html` on the Desktop.

## Design Tokens (CSS Custom Properties)

Always use `var(--token)` in CSS — never hardcode hex values. All tokens are
defined in `theme.css` on `.gradio-container` and in the landing page's `:root`.

### Colors — Dark Theme (default)

| Token                     | Value                       | Usage                                         |
|---------------------------|-----------------------------|------------------------------------------------|
| `--color-bg`              | `#161310`                   | Page background, input backgrounds             |
| `--color-surface`         | `#1b1814`                   | Cards, panels, section boxes                   |
| `--color-surface-2`       | `#201d19`                   | Nested/elevated cards (e.g. queue items)       |
| `--color-surface-offset`  | `#1e1b17`                   | Toolbars, secondary surfaces                   |
| `--color-surface-offset-2`| `#242018`                   | Tertiary accent surfaces                       |
| `--color-surface-dynamic` | `#2d2920`                   | Scrollbar thumbs, hover highlights             |
| `--color-divider`         | `#2a2720`                   | Section dividers, subtle borders               |
| `--color-border`          | `#373330`                   | Card borders, input borders                    |
| `--color-text`            | `#cec8c0`                   | Primary body text                              |
| `--color-text-muted`      | `#7a7468`                   | Labels, captions, secondary info               |
| `--color-text-faint`      | `#524e48`                   | Placeholders, disabled text, timestamps        |
| `--color-text-inverse`    | `#1b1814`                   | Text on primary-colored backgrounds            |
| `--color-primary`         | `#e06438`                   | Buttons, links, h3 headings, accent highlights |
| `--color-primary-hover`   | `#d05025`                   | Button hover, interactive hover states         |
| `--color-primary-active`  | `#b84020`                   | Button active/pressed state                    |
| `--color-primary-highlight`| `#3d2418`                  | Selected row backgrounds, active indicators    |
| `--color-accent-soft`     | `rgba(224,100,56,0.10)`     | Subtle tinted backgrounds, hover fills         |

### Colors — Light Theme (landing page only, for reference)

| Token                     | Value       |
|---------------------------|-------------|
| `--color-bg`              | `#f5f0eb`   |
| `--color-surface`         | `#f8f4ef`   |
| `--color-text`            | `#221e17`   |
| `--color-text-muted`      | `#7a7265`   |
| `--color-primary`         | `#b84a1e`   |
| `--color-primary-hover`   | `#973d18`   |

## Typography

| Role             | Font Family                                | Source                                                                       |
|------------------|--------------------------------------------|------------------------------------------------------------------------------|
| Display / H1-H3 | `'Instrument Serif', Georgia, serif`       | `https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1`         |
| Body / UI        | `'Satoshi', 'Inter', system-ui, sans-serif`| `https://api.fontshare.com/v2/css?f[]=satoshi@300,400,500,600,700`           |

- All headings (`h1`, `h2`, `h3`) use **Instrument Serif italic**.
- Any element rendering the word "OpenClay" uses **Instrument Serif italic**.
- All body text, labels, inputs, and buttons use **Satoshi**.
- Headings use `line-height: 1.15` and `text-wrap: balance`.
- Body text uses `line-height: 1.6` and `max-width: 68ch` where applicable.

## Radius Scale

| Token            | Value      | Usage                    |
|------------------|------------|--------------------------|
| `--radius-sm`    | `0.375rem` | Focus rings, small chips |
| `--radius-md`    | `0.5rem`   | Inputs                   |
| `--radius-lg`    | `0.75rem`  | Inner cards, tags        |
| `--radius-xl`    | `1rem`     | Section boxes, cards     |
| `--radius-2xl`   | `1.5rem`   | Large panels, mockups    |
| `--radius-full`  | `9999px`   | Buttons, pills, badges   |

## Shadows

| Token          | Value                           |
|----------------|---------------------------------|
| `--shadow-sm`  | `0 1px 3px rgba(0,0,0,0.25)`   |
| `--shadow-md`  | `0 4px 16px rgba(0,0,0,0.35)`  |
| `--shadow-lg`  | `0 12px 40px rgba(0,0,0,0.45)` |

## Transitions

All interactive elements: `180ms cubic-bezier(0.16, 1, 0.3, 1)` via `--transition`.

## Buttons

- Background: `var(--color-primary)`
- Text: `#fff`
- Border: none
- Border-radius: `var(--radius-full)` (pill)
- Box-shadow: `0 2px 8px rgba(224,100,56,0.3)`
- Hover: `var(--color-primary-hover)`, shadow expands, `translateY(-1px)`
- Font: Satoshi, weight 500

## Cards / Section Boxes

- Background: `var(--color-surface)`
- Border: `1px solid var(--color-border)`
- Border-radius: `var(--radius-xl)`
- Shadow: `var(--shadow-sm)`
- Hover: border goes `var(--color-primary)`, bg goes `var(--color-accent-soft)`

## Inputs

- Background: `var(--color-bg)`
- Border: `1px solid var(--color-border)`
- Border-radius: `var(--radius-md)`
- Focus: border `var(--color-primary)` + `box-shadow: 0 0 0 2px var(--color-accent-soft)`
- Text: `var(--color-text)`
- Font: Satoshi

## File Upload / Drop Zones

- Border: `1.5px dashed var(--color-border)`
- Border-radius: `var(--radius-xl)`
- Hover: border `var(--color-primary)`, bg `var(--color-accent-soft)`

## General Rules

- **Always use CSS variables** — never hardcode hex in new CSS.
- Use `!important` where needed to override Gradio defaults.
- No white or gray Gradio default backgrounds should ever be visible.
- Gradio footer is hidden.
- Scrollbar: track `var(--color-bg)`, thumb `var(--color-surface-dynamic)`.
- `::selection` uses `rgba(224,100,56,0.2)`.
- `:focus-visible` uses `2px solid var(--color-primary)`, offset `3px`.
- Strong/bold text inside markdown sections uses `var(--color-primary)`.
- Respect `prefers-reduced-motion` — disable animations when active.
