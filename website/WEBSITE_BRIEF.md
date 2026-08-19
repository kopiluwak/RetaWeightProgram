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

1. ~~App Store / Google Play links `href="#"`~~ — **RESOLVED 2026-08-18.** Both App Store buttons
   are now non-clickable "Coming soon to the App Store" badges (`<span>`, not `<a>`), and both
   Google Play buttons were removed since Android isn't shipping. Nothing on the page is dead or
   claims a download that doesn't exist. See "Switching the store buttons on" below for the
   launch-day change.
2. ~~Social-proof bar~~ — **REMOVED 2026-08-18.** Held an invented "4.9 App Store rating" for an
   unreleased app plus three "As seen in" outlets (MenoWell, GLP-1 Digest, Strength Weekly) that
   had never covered us.
3. ~~Transformations section~~ — **REMOVED 2026-08-18.** Three fabricated testimonials with
   invented named people, invented weight-loss and lift numbers, and quotes naming tirzepatide
   and semaglutide.
4. `og:image` — no `og:image` tag exists at all (not a placeholder — genuinely absent). Add a real
   image and the tag before launch, or link previews render bare.
5. `mailto:support@glpsteel.com` — confirm this address exists (SES currently sends from no-reply@).
6. Nutrition features are marketed as live — don't publish until the food-scan feature ships.
7. Stats ("≈40% lean mass", "2× halve lean-mass loss") — directional figures from GLP-1 lean-mass literature; verify against sources you're comfortable citing before launch.

### Switching the store buttons on (launch day)

Two spots in `index.html`: the hero (`id="download"`) and the final CTA. Both currently render a
non-clickable badge. To go live, wrap each in an anchor and change the small line of text:

```html
<!-- from -->
<span class="inline-flex …" role="text">
  <svg …></svg>
  <span …><span …>Coming soon to the</span><span …>App Store</span></span>
</span>

<!-- to -->
<a href="https://apps.apple.com/app/idAPPLE_ID_HERE" class="inline-flex … hover:opacity-90 transition-opacity" aria-label="Download on the App Store">
  <svg …></svg>
  <span …><span …>Download on the</span><span …>App Store</span></span>
</a>
```

- `APPLE_ID_HERE` is the numeric Apple ID from **App Store Connect → your app → App Information**.
  It already exists (the app record was created for TestFlight) — but the URL **404s until the app
  is actually released**, which is why the badge exists rather than a pre-set link.
- Restore the `hover:` classes on the anchor; they were dropped from the span because a
  non-interactive element shouldn't have hover affordance.
- Then deploy via runbook §F — **the CloudFront invalidation is required**, or the old page
  persists for up to 24h.

**Android:** the Google Play markup is in git history (2026-08-18 commit). The FAQ still says
"iOS today, with Android on the way" — accurate once iOS is live, but revisit it if Android slips.

### Restoring social proof later

Both removed sections are recoverable from git history (`git log -p -- website/index.html`,
the 2026-08-18 commit). Before putting either back:

- **Ratings must be real and current.** Quote the actual App Store rating, or don't show one.
- **Testimonials need written permission** from a real user, and any number you print
  (weight lost, lifts added, protein averages) has to be one you can substantiate.
- **Be careful attributing results to a medication.** The removed quotes named tirzepatide and
  semaglutide by brand. Invented outcomes tied to a prescription drug are a materially bigger
  problem than ordinary marketing puffery — and that exposure is independent of Apple.
- Press logos need an actual article you can link to.

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
