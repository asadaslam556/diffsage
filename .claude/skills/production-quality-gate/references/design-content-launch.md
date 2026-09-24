# Design, content, accessibility, SEO, and launch reference

The patterns below are warning signals, not universal bans. Lucide, Inter, gradients, cards, shadows, rounded corners, and animation can be legitimate when they belong to an intentional design system. Fail the review when choices are generic, excessive, inconsistent, copied from templates, or disconnected from product and audience.

## Product identity

- [ ] Product has a defined audience, purpose, personality, brand voice, visual references, and success action.
- [ ] Typography, color, spacing, radius, border, shadow, icon, illustration, grid, and motion use named tokens and consistent rules.
- [ ] UI follows the existing design system; third-party components are adapted rather than shipped in obvious defaults.
- [ ] Hierarchy, density, alignment, rhythm, affordance, and contrast are intentional across real content.
- [ ] Product-specific screenshots, workflows, diagrams, data, or interactive demos prove what the product does.
- [ ] Design was tested with long names, translations, validation errors, empty data, large data, and realistic customer content.

## Vibe-coded visual and copy audit

Inspect and justify, redesign, or remove these common tells:

- [ ] Harsh, arbitrary, or excessive gradients.
- [ ] Purple-and-black, neon, rainbow, or basic pastel palettes chosen without brand rationale.
- [ ] Pure white backgrounds everywhere with no surface hierarchy or comfort consideration.
- [ ] Radial gradient orbs, blurred blobs, dot grids, generic glow, noise, or decorative backgrounds unrelated to the product.
- [ ] Excessive drop shadows, glows, borders, soft corner radii, glass/liquid-glass effects, and floating panels.
- [ ] Bento grids, three feature cards in a row, three pricing tiers, repeated equal cards, and centered hero/template composition used by default rather than content need.
- [ ] Colored left stripes on cards/callouts as generic decoration.
- [ ] Terminal-window/code-window visuals when the product is not developer-focused or the example is not real.
- [ ] Lucide or one generic icon set used everywhere without curation; sparkle icons, animated arrows, generic rockets/brains/shields, and icons that merely repeat labels.
- [ ] Emojis or checkmark bullets used as default visual design rather than brand-appropriate communication.
- [ ] Inter, Geist, or Space Grotesk used only because they are tool defaults; font choice lacks hierarchy, loading strategy, fallbacks, licensing, or brand fit.
- [ ] Hover animation on every object, decorative motion, looping gradients, parallax, or motion without reduced-motion support and functional purpose.
- [ ] “It’s not X, it’s Y,” “revolutionize,” “unlock,” “supercharge,” “seamless,” “robust,” “delve,” “leverage,” “game-changing,” and similar generic AI/marketing constructions.
- [ ] Excessive em dashes, sentence fragments, uniform three-part lists, fake precision, generic headings, repeated cadence, or text that could describe any product.
- [ ] Fake testimonials, invented customer logos, fake ratings, fabricated usage numbers, unsupported “trusted by,” invented awards, or misleading badges.
- [ ] No real product demo, screenshots, proof, documentation, pricing explanation, limitations, or contact path.
- [ ] No skeleton/loading feedback for content whose delay or layout shift makes a placeholder useful; do not add skeletons to instantaneous actions or where a spinner/progress label is clearer.
- [ ] No Terms of Service, privacy policy, cookie controls, cancellation/refund terms, accessibility/contact information, or required business identity for the actual service and jurisdiction.

## UX completeness

- [ ] Clear, specific primary call to action appears above the fold when conversion is the page's purpose.
- [ ] CTA accurately describes the next action; no vague “Get Started” when a more specific label is possible.
- [ ] Sticky mobile CTA is added only when helpful, non-obstructive, dismissible where needed, safe-area aware, and compatible with keyboard and cookie banners.
- [ ] Navigation, breadcrumbs where needed, deep links, browser history, refresh, focus restoration, and unsaved-change behavior work.
- [ ] Every async surface has an appropriate initial/loading/skeleton, empty, error, success, retry, offline, slow, and partial state.
- [ ] Forms preserve data on recoverable failure; show explicit field and summary errors; focus/announce errors; prevent duplicate submission; allow correction.
- [ ] Destructive and irreversible actions communicate consequences and require suitable confirmation/re-authentication.
- [ ] Confirmation/thank-you page or durable status state exists for submissions, orders, subscriptions, and other consequential actions; refresh does not duplicate the action.
- [ ] Custom 404 explains what happened, preserves brand and navigation, offers recovery/search/primary routes, and returns the correct HTTP status.
- [ ] Custom 401/403/500/offline/maintenance states exist where relevant and do not leak internal details.
- [ ] Real contact/support details and expected response behavior are visible; legal address and registration details appear where required.

## Responsive and device testing

- [ ] Use content-driven breakpoints; test narrow phone, common phone, tablet, laptop, desktop, zoom, portrait/landscape, and safe areas.
- [ ] No horizontal overflow, clipped controls, hidden content, overlapping sticky elements, tiny targets, broken tables, or unreadable line lengths.
- [ ] Mobile keyboard does not hide the focused field or CTA; input types and autocomplete are appropriate.
- [ ] Touch, mouse, keyboard, and screen reader interactions all work; hover is not the only path.
- [ ] Test supported browsers and at least one representative real low/mid-range device when possible.
- [ ] Test throttled/poor network, high latency, loss, offline transitions, failed/retried requests, cached/stale data, and disabled/slow JavaScript.
- [ ] Do not let skeletons or optimistic UI hide permanent failures.

## Accessibility

- [ ] Target required WCAG version/level, normally WCAG 2.2 AA unless policy says otherwise.
- [ ] Use semantic HTML, correct headings, landmarks, lists, buttons, links, tables, form labels, fieldsets, and native controls before ARIA.
- [ ] All functionality is keyboard operable; focus order is logical, focus visible and unobscured, and focus is managed for dialogs/routes/errors.
- [ ] Interactive names, roles, values, states, instructions, errors, and status changes are available to assistive technology.
- [ ] Meaningful images have concise contextual alt text; decorative images use empty alt; complex charts have text alternatives/data.
- [ ] Captions/transcripts/audio descriptions are present when required.
- [ ] Text/non-text contrast, color independence, zoom, reflow, orientation, text spacing, target size, dragging alternatives, timing, flashing, and reduced motion pass.
- [ ] Authentication does not rely on inaccessible cognitive tests without an alternative.
- [ ] Automated accessibility scan is supplemented with keyboard and representative screen-reader testing.

## Metadata, crawlability, and social sharing

- [ ] Every indexable page has a unique, concise, accurate `<title>` and useful meta description aligned with actual content.
- [ ] One clear page heading and semantic hierarchy; canonical URL, language, locale, and `hreflang` where applicable are correct.
- [ ] Open Graph includes page-appropriate `og:title`, `og:type`, canonical `og:url`, representative `og:image`, image dimensions/type/alt, and description; equivalent platform cards are tested where relevant.
- [ ] Favicon/app icons, web manifest/theme metadata, and browser/device assets are correct across themes/sizes.
- [ ] `robots.txt` is syntactically valid, references sitemap, and does not expose secrets or attempt to protect private content.
- [ ] Private/staging/admin pages use authentication and correct `noindex`/headers; robots exclusion is not treated as access control.
- [ ] `sitemap.xml` contains canonical public URLs only, returns successfully, has accurate modification data when used, and is submitted/declared where appropriate.
- [ ] SPA/rendered routes are crawlable with stable URLs and meaningful server-rendered or accessible DOM content where SEO is required.
- [ ] Redirects, canonicalization, trailing slash, HTTP/HTTPS, www/non-www, duplicate query URLs, broken links, and 404 status behavior are correct.
- [ ] Structured data is valid, visible-content-aligned, non-misleading, and appropriate to the page.
- [ ] Meaningful image alt text, descriptive filenames/context, and image sitemap where useful are present; alt is not keyword stuffing.

## Legal, privacy, analytics, and trust

- [ ] Privacy policy describes actual data and vendors, not generic template claims.
- [ ] Terms of Service match the service, eligibility, accounts, acceptable use, IP, payment, subscription, cancellation, refunds, disclaimers, liability, termination, dispute terms, and governing jurisdiction as applicable.
- [ ] Legal counsel or authorized owner reviews legal text when consequences warrant it; the agent does not claim legal compliance.
- [ ] Cookie/storage banner appears only where legally required but, when required, blocks non-essential technologies until valid consent.
- [ ] Accept/reject/customize choices are clear and appropriately balanced; no preselected non-essential categories, deceptive design, or consent wall without basis.
- [ ] Consent can be withdrawn as easily as granted; preferences and consent evidence are retained appropriately.
- [ ] Analytics, ads, pixels, session replay, chat, embeds, A/B testing, and third-party scripts honor consent and privacy signals as required.
- [ ] Analytics excludes sensitive fields/pages and internal/test traffic where appropriate; events are named, documented, deduplicated, and validated.
- [ ] Contact identity, geographical address, email/phone, registration/tax/professional details, prices, taxes, delivery, cancellation, and complaint information appear where jurisdiction/business model requires them.
- [ ] No fake testimonial, logo, review, counter, certification, security claim, accessibility claim, performance claim, or guaranteed outcome.

## Performance and images

- [ ] Establish budgets for JavaScript/CSS/fonts/images/requests and critical user metrics.
- [ ] Measure representative routes on mobile and desktop with field data when available and laboratory tests otherwise.
- [ ] Optimize LCP, INP, and CLS; no layout shifts from missing image/media dimensions, banners, ads, or late fonts.
- [ ] Compress and resize images for rendered dimensions and device density; use responsive `srcset`/`sizes` or framework equivalents.
- [ ] Use appropriate modern formats with fallbacks; preserve acceptable visual quality, alpha, animation, and accessibility.
- [ ] Lazy-load below-fold images/iframes, but do not lazy-load the LCP/hero asset; prioritize critical assets intentionally.
- [ ] Specify image width/height/aspect ratio, avoid oversized mobile downloads, and inspect decoded memory cost.
- [ ] Subset/preload fonts carefully, use suitable `font-display`, minimize variants, and provide system fallbacks.
- [ ] Code split by actual route/feature, remove unused CSS/JS, limit third-party scripts, cache immutable assets, compress transfer, and avoid hydration/client waterfalls.
- [ ] Test slow network and low-end CPU; critical content and actions remain usable before optional enhancement.

## Pre-launch security checklist supplied by project owner

Every item below is mandatory when applicable and is expanded by the engineering reference:

- [ ] Remove test data.
- [ ] Hide API keys; more precisely, remove from code/client/artifacts, store in approved secret management, and rotate any exposed key.
- [ ] Protect admin routes with server-side authentication, authorization, re-authentication/MFA where appropriate, rate limits, and audit logs.
- [ ] Check authentication and permissions across roles, objects, fields, tenants, APIs, jobs, files, and admin actions.
- [ ] Secure database and storage rules with deny-by-default and ownership/tenant tests.
- [ ] Validate user inputs server-side and encode outputs by context.
- [ ] Add and test API rate limits, quotas, body limits, timeouts, and expensive-operation controls.
- [ ] Test file uploads for authorization, size/type/content, malicious files, safe storage, downloads, and cleanup.
- [ ] Handle API errors, timeouts, retries, partial failures, and unavailable dependencies.
- [ ] Remove debug logs, debug routes, breakpoints, development tooling, and verbose mode.
- [ ] Hide sensitive error details from users while retaining safe correlation and server diagnostics.
- [ ] Test mobile layouts, touch, keyboard, zoom, safe areas, and real content.
- [ ] Test slow internet, latency, loss, offline/reconnect, retry, stale data, and low-end devices.
- [ ] Test payments and webhooks end-to-end, including signatures, raw body, idempotency, replay, ordering, retries, refunds, disputes, and reconciliation.
- [ ] Try to break the app through abuse cases, authorization bypass, malformed/oversized input, concurrency, replay, business-logic abuse, and resource exhaustion; perform authorized penetration testing in scope.

## Website launch completeness checklist supplied by project owner

- [ ] Create a useful custom 404 page with correct status and recovery paths.
- [ ] Put a clear, accurate primary CTA above the fold when appropriate.
- [ ] Add a unique, descriptive meta title for every indexable page.
- [ ] Add a useful, page-specific meta description.
- [ ] Add and test a representative Open Graph image and metadata.
- [ ] Set favicon and relevant app icons.
- [ ] Create and validate `robots.txt`; never use it as access control.
- [ ] Create and validate `sitemap.xml` with canonical public URLs.
- [ ] Add contextual alt text to every meaningful image and empty alt to decorative images.
- [ ] Test content-driven mobile breakpoints and representative devices.
- [ ] Add a sticky mobile CTA where it improves the journey without obscuring content or accessibility.
- [ ] Implement appropriate loading/skeleton/progress states.
- [ ] Implement explicit, accessible form validation and submission error states.
- [ ] Build a thank-you/confirmation or durable status page/state for consequential submissions.
- [ ] Publish an accurate privacy-policy page when data is processed or otherwise required.
- [ ] Publish accurate Terms of Service when appropriate/required.
- [ ] Add a compliant cookie/storage consent mechanism where legally required.
- [ ] Install analytics only with appropriate consent, data minimization, event QA, sensitive-data exclusions, and disclosure.
- [ ] Provide real contact and business/address/registration details where required; never fabricate them.
- [ ] Compress, resize, responsively serve, dimension, and correctly prioritize images.

## Human visual and content review

Before launch, a human must inspect the real deployed site, not screenshots alone:

- [ ] First impression communicates product, audience, differentiation, and next action without generic filler.
- [ ] Visual system feels coherent and product-specific, not like an untouched AI/component template.
- [ ] Every claim, testimonial, logo, metric, screenshot, price, policy, contact, and legal identity is real and current.
- [ ] Real product workflows are demonstrated rather than represented only by abstract cards or decorative terminal windows.
- [ ] Copy sounds like the intended organization, varies naturally, and gives concrete information.
- [ ] Desktop/mobile, light/dark themes, loading/error/empty states, and long localized content look intentional.
