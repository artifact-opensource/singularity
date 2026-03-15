# Artifact Virtual — Brand Guidelines (Typography & Visual Language)

> Source of truth. All public-facing pages MUST conform to these standards.
> Reference implementation: singularity.artifactvirtual.com

## Typography

### Font Stack
```
--font-sans:  'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif
--font-mono:  'JetBrains Mono', 'SF Mono', 'Fira Code', ui-monospace, monospace
```

### Google Fonts Import (REQUIRED on every page)
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&family=JetBrains+Mono:ital,wght@0,100..800;1,100..800&display=swap" rel="stylesheet">
```

### BANNED Fonts
- ❌ Cormorant Garamond (currently on artifactvirtual.com — MUST BE REPLACED)
- ❌ Source Code Pro
- ❌ Any serif font for body text
- ❌ System defaults without Inter loaded

### Usage Rules
| Element | Font | Weight | Size |
|---------|------|--------|------|
| Body text | Inter | 400 | 0.95-1rem |
| Headings | Inter | 600-800 | 1.5-3rem |
| Subheadings | Inter | 500 | 1.1-1.3rem |
| Navigation | Inter | 500 | 0.875rem |
| Code/data/metrics | JetBrains Mono | 400-500 | 0.85-0.95rem |
| Quotes | JetBrains Mono | 400 italic | 0.85rem |
| Buttons/CTAs | Inter | 600 | 0.875rem |
| Status badges | JetBrains Mono | 500 | 0.75rem |

### Letter Spacing
- Headings: -0.02em to -0.04em (tighter)
- Body: 0 (default)
- Mono/data: 0.02em (slightly open)
- All-caps labels: 0.08em

## Color System

### Core Palette (Dark Theme — DEFAULT)
```css
--bg:               #09090F;     /* Page background */
--surface:          #0D0D1A;     /* Card/panel background */
--surface-raised:   #12122A;     /* Elevated surfaces */
--surface-border:   #1A1A35;     /* Borders */

--text-bright:      #FFFFFF;     /* Headlines, primary text */
--text-primary:     #E0E0E0;     /* Body text */
--text-secondary:   #8888AA;     /* Muted, labels, descriptions */

--accent:           #7C6AFF;     /* Primary brand purple */
--accent-soft:      rgba(124, 106, 255, 0.15);  /* Purple tint for backgrounds */
--accent-glow:      rgba(124, 106, 255, 0.3);   /* Glow effects */

--success:          #22C55E;     /* Green — operational, positive */
--warning:          #EAB308;     /* Yellow — warnings */
--danger:           #EF4444;     /* Red — errors, critical */
```

### BANNED Colors
- ❌ Pure white backgrounds (#FFFFFF as bg)
- ❌ Bright saturated colors without opacity
- ❌ Any brand purple that isn't #7C6AFF or derived from it

## Logo Usage

### Rules
1. Logo IS the title — no separate text title needed next to logo
2. Wordmark "Artifact Virtual" MAY appear next to logo in nav, font: Inter 600
3. Logo must have proper spacing (min 16px padding)
4. No logo stretching, rotation, or color modification
5. White logo on dark backgrounds only
6. Logo file: `av-logo-white.png` (or SVG when available)

### Navigation Bar
```
[Logo] Artifact Virtual    Products  About  GitHub  [CTA Button →]
```
- Logo left-aligned, nav links right-aligned
- CTA button uses accent color background
- Font: Inter 500, 0.875rem
- Background: transparent or surface with backdrop-blur

## Layout & Spacing

### Radius System
```css
--radius-xs:  6px;   /* Badges, small elements */
--radius-sm:  8px;   /* Buttons, inputs */
--radius-md:  12px;  /* Cards */
--radius-lg:  16px;  /* Sections, modals */
--radius-xl:  24px;  /* Hero elements */
```

### Spacing
- Section padding: 80-120px vertical
- Card padding: 24-32px
- Grid gap: 16-24px
- Max content width: 1200px (centered)

## Component Patterns

### Cards
```css
background: var(--surface);
border: 1px solid var(--surface-border);
border-radius: var(--radius-md);
padding: 24px;
```

### Buttons
```css
/* Primary CTA */
background: var(--accent);
color: white;
border-radius: var(--radius-sm);
padding: 10px 20px;
font: 600 0.875rem Inter;

/* Ghost/Secondary */
background: transparent;
border: 1px solid var(--surface-border);
color: var(--text-primary);
```

### Status Indicators
```css
/* Online/Active */
color: var(--success);
font-family: var(--font-mono);
font-size: 0.75rem;

/* With pulse animation */
.pulse::before { animation: ping 1.5s infinite; }
```

## Sidebar / Navigation Standards (Multi-page apps)

### Structure
1. Logo at top (no text title — logo IS the title)
2. Primary nav items grouped by function
3. Apps section: group all app links together
4. External links open in new tab with `rel="noopener"`
5. Active page highlighted with accent-soft background
6. Mobile: hamburger menu, slide-in panel

### Required Links (every AV page)
- Home (artifactvirtual.com)
- Products (anchored or page)
- Research (research.artifactvirtual.com)
- GitHub (github.com/Artifact-Virtual)
- ERP (erp.artifactvirtual.com)

## Page-Specific Notes

### artifactvirtual.com (MAIN — NEEDS TYPOGRAPHY FIX)
- Currently uses Cormorant Garamond — MUST switch to Inter
- Source: /var/www/html/ (crypt repo)
- Fix font imports, all font-family declarations

### singularity.artifactvirtual.com (REFERENCE — GOOD)
- This IS the reference implementation
- Typography correct: Inter + JetBrains Mono
- Colors correct: #7C6AFF accent, dark theme

### gdi.artifactvirtual.com (MOSTLY GOOD)
- Typography already Inter — just verify consistency
- Hamburger menu has layout issues — needs fix
- Source: /var/www/gdi/

### arc.artifactvirtual.com
- Verify Inter + JetBrains Mono
- Verify #7C6AFF accent
- Source: /var/www/arc/

### research.artifactvirtual.com
- Verify typography matches
- Fix any broken paper links
- Source: /var/www/research/

### comb.artifactvirtual.com
- Already uses Inter + JetBrains Mono — verify exact weights
- Verify color consistency
- Source: /var/www/comb/

### gladius-three.vercel.app (GLADIUS)
- Verify fonts and colors
- Source: external Vercel deployment

### Hugging Face Spaces
- All spaces need polished READMEs
- All paper links must work
- Consistent branding in space descriptions
- HF tokens currently expired — need Ali to re-auth

### ERP (erp.artifactvirtual.com)
- Currently "theme-less" — needs the brand applied
- Dark theme already set as default
- CSS has Inter + JetBrains Mono
- Needs accent color alignment to #7C6AFF

## Audit Checklist (Per Page)
- [ ] Inter loaded via Google Fonts
- [ ] JetBrains Mono loaded via Google Fonts
- [ ] No banned fonts present
- [ ] Body font-family set to Inter
- [ ] Mono elements use JetBrains Mono
- [ ] Background: dark (#09090F or close)
- [ ] Accent: #7C6AFF
- [ ] Logo present, no text title duplicating logo
- [ ] Navigation consistent with standard
- [ ] All internal links working
- [ ] All external links open in new tab
- [ ] Mobile responsive
- [ ] No broken images
- [ ] Proper meta tags (og:title, og:description, og:image)
