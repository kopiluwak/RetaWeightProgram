# GLP Steel — Website SEO, Domains & Content Brief

Companion to `website/index.html`. Site is a single file — host as-is on Vercel/Netlify (drop in a folder, deploy) or paste sections into Framer.

## SEO meta (already in the HTML)

**Title (60 chars target):**
`GLP Steel — Keep the Muscle. Lose the Weight. | Strength Training for GLP-1 Users`

**Meta description:**
`On a GLP-1? Snap a photo of your equipment and get a science-backed 3, 4, or 5-day strength program built to preserve muscle in a deficit. Plus high-protein recipes from a photo of your fridge. $15 once. No subscription.`

**Alternate titles to A/B test:**
- `GLP Steel: Muscle-Preserving Workouts for GLP-1 Users | $15 Once`
- `Stop Losing Muscle on Ozempic, Zepbound & Retatrutide — GLP Steel`
- `Home Workouts From a Photo of Your Equipment | GLP Steel`

**Target keywords:** muscle loss GLP-1, ozempic muscle loss, strength training semaglutide, tirzepatide protein intake, retatrutide muscle, home workout app no subscription, protein recipes GLP-1, equipment-based workout generator.

**Notes:** brand-name drug keywords (Ozempic, Zepbound) are fine in blog/SEO content but avoid implying endorsement by the manufacturers. Add an `og:image` (1200×630) before launch — a phone screenshot on the dark ember gradient.

## Domain ideas

You already own **glpsteel.com** — use it. Worth also grabbing (redirects + brand protection):
- glpsteel.app
- getglpsteel.com
- steel.fitness (if available; premium)
- keepthemuscle.com (campaign/landing domain)
- glpstrong.com

## Pre-launch checklist (placeholders to replace)

1. App Store / Google Play links — currently `href="#"` (2 spots: hero + final CTA).
2. Social-proof bar — rating "4.9" and press names (MenoWell, GLP-1 Digest, Strength Weekly) are invented placeholders. Replace or delete.
3. Transformations section — all three stories are fabricated and labeled "placeholder testimonial" in visible text and HTML comments. Replace with real, permission-granted stories or remove.
4. `og:image` — add a real image + `og:image` tag.
5. `mailto:support@glpsteel.com` — confirm this address exists (SES currently sends from no-reply@).
6. Nutrition features are marketed as live — don't publish until the food-scan feature ships.
7. Stats ("≈40% lean mass", "2× halve lean-mass loss") — directional figures from GLP-1 lean-mass literature; verify against sources you're comfortable citing before launch.

## Content brief by section

**Hero.** Job: name the fear (muscle loss) and the effortless fix (one photo) in 5 seconds. Headline leads with loss-aversion; subhead quantifies the problem then presents the two-photo promise. CTA = store badges + price-transparency line ("$15 once") to disarm subscription fatigue immediately.

**Social proof bar.** Job: borrowed credibility above the fold's second scroll. Keep to one line; swap in real rating + press when available.

**Problem ("The scale is lying to you").** Job: educate + create urgency without fear-mongering. Three stat cards give scannable evidence. Tone: authoritative, clinical-adjacent, never anti-medication — GLP-1s are framed as remarkable, the app as the missing companion.

**Features (6 cards).** Job: translate features into outcomes. Order matters: the two camera features first (the "wow"), then programming credibility, then analytics/gamification (retention), privacy last as trust-closer. Each card = verb-led headline + 2-sentence benefit copy.

**How it works (4 steps).** Job: collapse perceived effort. "Under 5 minutes" headline sets the expectation; steps end on nutrition to bridge into protein messaging.

**Transformations.** Job: make the outcome concrete with paired numbers — weight *down*, strength *up*. That contrast IS the product story. Real stories should always pair a scale number with a strength/protein number.

**Pricing.** Job: weaponize the one-time price against subscription apps. Anchor against $10–30/mo competitors and $200/mo trainers. The $1 scans are framed as pay-for-what-you-use fairness, not upsell. Single card, no tiers — simplicity is the message.

**FAQ.** Job: handle the real objections — "not on GLP-1?", equipment, pricing honesty, photo privacy, beginner fear, protein rationale, platforms. Native `<details>` accordion = accessible with zero JS. Medical-advice disclaimer lives in the protein answer + footer.

**Final CTA.** Job: urgency via irreversibility ("muscle you won't get back easily") + minimal friction ("one photo away"). Repeats badges so no scroll-back needed.

**Footer.** Product links, privacy/support (backend already serves /privacy and /support), medical disclaimer.

## Tech notes

- Tailwind via CDN (fine for launch; for max Lighthouse score later, compile with the Tailwind CLI and inline the CSS).
- Dark mode default, toggle persists in localStorage, no flash-of-wrong-theme (inline script in head).
- Animations: IntersectionObserver reveals, `prefers-reduced-motion` respected. Smooth scroll via `scroll-smooth`.
- Accessibility: semantic landmarks, aria-labels on nav/toggle/badges, native accordion, focus-visible states from Tailwind defaults.
- No build step, no external images — loads fast anywhere.
