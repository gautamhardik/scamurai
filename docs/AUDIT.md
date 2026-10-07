# Asli: final audit report

**Date:** 7 October 2026.

**Scope:** the whole repository at commit `e46a3dc` (after the UI redesign) through the fixes listed below.

**Method:**
1. Read the source end to end.
2. Wrote adversarial probes that reproduced each suspected issue before touching code (`30` probes, no network).
3. Ran the app in a browser at 320, 375 and 1280 px.
4. Ran a 30-message evaluation live against SerpApi and OpenRouter.
5. Made a fresh `git clone` to test the judge's setup.
6. Ran a dependency scan.

Fixes that can be tested offline have regression tests; UI and timing fixes were verified in the browser or by code review. Every number below was measured, not estimated.

---

## 1. Executive verdict

| Area | Score | Why |
|---|---:|---|
| Engineering | 8/10 | A clean, deterministic pipeline with bounded loops and 256 offline tests. The audit found real logic bugs in trust handling, and they are now fixed. |
| Security | 8/10 | No SSRF surface, a strict CSP, upload hardening, and now DNS-rebinding and CSRF protection. It is a local-first app with no authentication by default. |
| AI reliability | 7/10 | The model only extracts, its output is grounded and it can't reach the score. Screenshot transcription still has to be trusted. |
| SerpApi integration | 9/10 | Six engines, each answering a distinct question, with cache, dedupe, budgets and replay. A median of 2 searches per check. |
| UX | 8/10 | Clear on first view, evidence is one click away, works on mobile, and respects reduced motion. Live checks are slow. |
| Performance | 6/10 | Cached checks take 15 ms (median). Live checks take 23 s (median) and 65 s (90th percentile), almost all of it the free AI model. |
| Hackathon competitiveness | 8/10 | A strong, demonstrable SerpApi story with measured results. The repository isn't public yet and there is no video yet. |
| **Overall** | **8/10** | |

---

## 2. Critical findings (P0)

| ID | Finding | Impact | Fixed? | Verification |
|---|---|---|---|---|
| A1 | **Trust poisoning: a website could vouch for itself.** For organisations not on the curated list, the "official site" came from the top search result. A made-up company's own site ranks first for its own name, so it then "confirmed" its own link (T2) and number (T1). | A fake job offer was rated **No major warning signs** (LOW_RISK). | Yes | Probe: LOW_RISK → UNVERIFIED. `test_a_message_domain_cannot_confirm_itself` |
| A2 | **Planted helpline counted as official.** A number found on a big platform's *product page* (amazon.in/dp/…) counted as the organisation's own. Scammers plant fake "customer care" numbers in listings and Q&A. | A fake Amazon customer-care number was rated LOW_RISK. | Yes | Probe: LOW_RISK → SUSPICIOUS. `test_number_on_a_marketplace_product_page_is_not_official` |
| A3 | **The repository was missing its knowledge base.** `.gitignore` had `data/`, which matched every directory named `data`, so `src/asli/knowledge/data/` (official domains, source classes) was never committed. | A fresh clone failed **37 tests**, and the app crashed on its first check. CI would be red, and judges couldn't run it. | Yes | Fresh clone: 37 failed → 256 passed. `asli demo` from the clone streamed a full report over HTTP. |

## 3. High-priority findings (P1)

| ID | Finding | Impact | Fixed? | Verification |
|---|---|---|---|---|
| B1 | **A genuine SBI debit alert scored High risk (65)** in the live evaluation. There were four root causes, listed below this table. | A false alarm on the most common genuine SMS type. | Yes | Live re-run: LOW_RISK (SBI's contact page confirms the number). The regression test fails on the pre-fix commit (all five false signals present) and passes now. |
| B2 | **False reassurance.** *No major warning signs* was given when two searches returned *anything*, even unrelated pages. | A scam with no web footprint looked safe. | Yes (gate G4) | Probe: LOW_RISK → UNVERIFIED. `test_unrelated_results_are_not_reassurance` |
| B3 | **CSRF.** Any website the user visited could POST to `127.0.0.1:8000/api/investigations`. | Drive-by spending of the user's SerpApi credits. | Yes | Probe: 200 → 403. `test_cross_site_posts_are_refused` |
| B4 | **DNS rebinding.** Any `Host` header was accepted. | A rebinding page could read stored reports (which contain phone numbers). | Yes | Probe: 200 → 400. `test_foreign_host_header_is_refused` |
| B5 | **An unparseable AI response crashed the check.** If OpenRouter returned a 200 response with a non-JSON body (an HTML error page), `r.json()` raised. | The user got "Something went wrong" instead of a rules-based report. | Yes, plus a fallback | Probe: crash → SUSPICIOUS via rules. `test_unparseable_llm_response_degrades_to_rules` |
| B6 | **Three signals never fired.** "Not found" signals (W4 website has no track record, W5 company not found, W10 job not listed) cited only the message, so the citation gate always dropped them. That left 3 of the 33 advertised signals dead. | Missed evidence. | Yes: they now cite the search itself, as a link that re-runs it | Scenarios: W4 now fires for `bijli-bill-pay.top` and `nike-outlet-sale.shop`. The UI shows "Search Asli ran". |
| B7 | **Keyboard users couldn't add a screenshot.** The button was a `<label>` for a hidden file input, and labels aren't focusable. | An accessibility blocker. | Yes | `#pick-file` is a real button with `tabIndex` 0. |

**Root causes of B1:**
1. News about *SBI scams* (W6/W7) counted against a message that showed no scam mechanics.
2. Helpline directories ("SBI complaint number 1800 11 2211…") counted as scam reports because of the words "complaint" and "fraud".
3. The merchant UPI ID in "debited… to VPA swiggy@icici" was treated as a request to pay.
4. The official-number check searched only `sbi.co.in`, while SBI's contact pages now live on `sbi.bank.in`.

## 4. Medium and low findings (P2/P3)

| ID | Sev | Finding | Fixed? | Verification |
|---|---|---|---|---|
| C1 | P2 | Evidence wording overstated the evidence: "Matches a reported scam" (it's news about *this kind* of scam), "the same photo" (Lens returns near-identical matches) and "Google has no results" (actually, no result *mentions* the domain). | Yes, in EN/HI/Hinglish | Manual review |
| C2 | P2 | The prompt-injection detector missed 6 of 8 adversarial phrasings, including Hindi and Hinglish ones. | Yes | 8/8 caught, 0/9 false positives (parametrized tests) |
| C3 | P2 | `amazonhr.jobs@ybl` (a UPI ID) was read as the website `amazonhr.jobs` (`.jobs` is a real TLD), producing a "website has no track record" flag for a site that doesn't exist. | Yes | `test_upi_id_is_not_mistaken_for_a_website` |
| C4 | P2 | A plain request to pay (normal in genuine bills) unlocked scam-pattern news, so a bill reminder scored SUSPICIOUS 42. | Yes | Live re-run: UNVERIFIED 18 |
| C5 | P2 | A utility, bank or authority that asks you to call a personal mobile was flagged only when the organisation was named. | Yes (generic I6) | Live: both electricity scams are flagged |
| C6 | P2 | Screenshot decoding (up to 40 MP) ran on the event loop. | Yes (`to_thread`) | Tests |
| C7 | P2 | Expired search-cache rows (whose params contain the searched phone numbers) were never deleted, and pruning ran only at startup. | Yes (hourly; deletes expired rows) | `test_prune_drops_expired_search_cache` |
| C8 | P2 | AI retries could hold "Reading the message" for about 4 minutes (2 × 120 s). | Yes (one 120 s budget) | Code review |
| C9 | P3 | The amount regex was quadratic: 528 ms on 4,000 digits. | Yes: 12 ms | `test_amount_regex_is_linear_and_reads_hindi_prefix` |
| C10 | P3 | Hindi "रु. 500" amounts weren't extracted, and Hinglish task-scam wording ("videos like karo… kamao") was missed. | Yes | Tests, evaluation |
| C11 | P3 | Toll-free numbers were shown regrouped ("1800 112 211" instead of "1800 11 2211"). | Yes | `test_toll_free_numbers_keep_their_grouping` |
| C12 | P3 | Hindi reports had no `lang` attribute, so screen readers used an English voice. | Yes | Checked in the browser (`lang="hi"`) |
| C13 | P3 | Link and phone placeholders had 3:1 contrast, and budget-skipped checks read "couldn't run". | Yes | Visual check |
| C14 | P3 | The README was stale: 224 tests, the old LOW_RISK rule, overstated wording. | Yes | This report |

**Found during the redesign (before the audit), also fixed:**
- The hero's gradient text painted through hidden flip words.
- Descenders were clipped inside the gradient.
- The flip-word width was measured before the font loaded.
- Animation frames pause in background tabs and could stall a submit; there are now timer fallbacks.
- Static files are now revalidated, so UI updates show up.

## 5. Bugs fixed: root cause and change

- **A1:** `resolve_official` accepted any knowledge-graph or top-result domain. It now skips domains the message itself supplies ("a website can't vouch for itself"). Curated domains are unaffected.
- **A2:** Owner mentions now require an official or curated domain *and* a contact/help page URL or title *and* a domain not supplied by the message.
- **A3:** `.gitignore` `data/` → `/data/`; the knowledge files are now tracked.
- **B1:** Four changes:
  - W6/W7 count only alongside a "hook" signal: a request, identity mismatch, report, price anomaly and so on, but not urgency, a plain payment request or "not found".
  - Phone and UPI reports need scam-specific words (`report_hits`).
  - UPI IDs in transaction notices aren't requests (`upi_is_requested`), and they aren't searched.
  - The official-number query covers the main domain plus the `.bank.in` domain (`(site:sbi.co.in OR site:sbi.bank.in)`). Absence is weaker evidence for toll-free numbers.
- **B2:** Gate G4: LOW_RISK needs a trust signal with w·c ≥ 0.3.
- **B3/B4:** The middleware refuses unknown `Host` values, and refuses POSTs whose `Origin` doesn't match or whose `Sec-Fetch-Site` is `cross-site`. `ASLI_ALLOWED_HOSTS` covers deployments.
- **B5:** The LLM client handles non-JSON and non-dict bodies. The orchestrator falls back to rules-only extraction if extraction raises at all.
- **B6:** A new evidence kind, `search`: the query with a Google link to re-run it. It has no domain, so it never counts as a source.

## 6. Security findings

| Area | Result |
|---|---|
| **SSRF** | Not possible by design: Asli never fetches user URLs. 12 hostile URLs were rejected at input: `127.0.0.1`, `localhost`, `[::1]`, `10/8`, `192.168/16`, `169.254.169.254`, `0x7f000001`, `2130706433`, `file:`, `javascript:`, `data:` and `ftp:`. IP-literal links in message text are never searched. |
| **Uploads** | Rejected: a 20000×20000 PNG bomb (47 KB), a 49 MP PNG, a JPEG/HTML polyglot, a truncated PNG, SVG and EXE. All under 10 ms. Images are re-encoded (EXIF stripped). |
| **Prompt injection** | Message and screenshot text is delimited, nonce-tagged untrusted data, and the model returns closed-vocabulary JSON. Values are grounded before use. **Search results never reach a model**: the only model call is extraction, in `llm/extract.py`. Injection attempts are flagged (M5) in EN/HI/Hinglish. |
| **Web** | Strict CSP, `textContent` only, no CORS, Host allow-list, cross-site POSTs refused, rate limit 6 per 10 minutes per IP, 2 concurrent checks, 5 MB body cap before parsing, optional access token. |
| **Secrets** | Keys are `SecretStr`, never sent to the browser and redacted from logs. A test scans every tracked file for the real `.env` values. `.env` isn't tracked (verified in the fresh clone). |
| **Dependencies** | `pip-audit` on the 35 locked runtime packages: **no known vulnerabilities**. All direct dependencies are used. |
| **Remaining** | No authentication by default; the app is designed for localhost. Deploying it publicly needs `ASLI_ACCESS_TOKEN` and `ASLI_ALLOWED_HOSTS`. **Both API keys were shared in a chat during development and must be rotated after the hackathon.** |

## 7. SerpApi audit

| Engine | Correct? | Meaningful? | Efficient? | Evidence quality | Changes in this audit |
|---|---|---|---|---|---|
| `google`: official site | Yes | Identity baseline (I2/T2) | Skipped for about 50 curated organisations | KG > top result. Message domains are now excluded (A1). | A1 |
| `google`: number, UPI, domain reputation | Yes | W1/W12/W2/W4 | Up to 2 numbers, 1 UPI and 2 domains. Merchant UPIs in notices are no longer searched. | Same-result match plus scam-specific words; independent domains | B1, B6, C3 |
| `google`: `site:` official-number check | Yes | T1/W3 | Round 2, only when an organisation and a number exist and the number isn't already confirmed | Contact/help pages only | `.bank.in` coverage, toll-free confidence |
| `google_news` | Yes | W6/W7 context | 1 per check; curated per-scheme query | 5-year freshness; independent outlets | Hook requirement (B1, C4); wording (C1) |
| `google_lens` + Image API | Yes | W9 photo reuse; real prices for W8 | Image API costs 0 credits; keyed by image hash | Same-product filter, IQR | Wording (C1) |
| `google_shopping` | Yes | W8/T5 price | Only when Lens finds fewer than 3 prices | Title-matched offers | None |
| `google_jobs` | Yes | T3/W10 | Job offers with a company only | Company + role match | W10 now cites the search (B6) |
| `google_maps` | Yes | T4/W11 | Only when an address exists | Residential-type heuristic | None |

**Could SerpApi be removed without losing the product?** No. With rules only, the same 30 messages give **5/10** scam recall instead of 10/10, and 3/10 genuine confirmations instead of 6/10.

**Efficiency (measured):**
- A median of **2** searches per uncached check, and a maximum of 6 (cap 8).
- The full 30-message live evaluation cost **21 credits**. Re-running it cost **1**.
- Identical queries are shared within a check, and "no results" answers are cached too.

## 8. AI and agent audit

- **Extraction.**
  - Phones, links, emails, UPI IDs and amounts come from deterministic extractors. Model-only values that don't appear in the input are dropped.
  - The model chooses only from closed lists (scheme, category, language).
  - Weakness: for screenshots, the haystack includes the model's own transcription.
- **Planner.**
  - Deterministic and template-based, with at most 8 searches in 2 fixed rounds.
  - No model in the loop after extraction, so nothing can make it run indefinitely.
- **Hard limits:**
  - 90 s search phase.
  - 2 attempts per SerpApi call, with timeouts of 25 s (Search), 40 s (Lens) and 60 s (Jobs).
  - One 120 s budget for the AI reader across its retry.
  - Rate and concurrency caps.
- **Grounding and hallucination.**
  - Every flag must cite evidence. Web and trust flags must cite a search result or a curated reference.
  - Templates generate all report text, so the model writes nothing the user reads.

## 9. Risk engine audit

The engine is a noisy-OR over w·c. Risk points = 100 · R · (1 − 0.75 T). Thresholds are 65 (high) and 35 (be careful). The gates:

| Gate | Rule |
|---|---|
| G1 | High risk needs a strong identity or web signal, or a critical request. |
| G2 | When only message patterns fired, the score is capped at 55. |
| G3 | Official confirmation together with a report on the same entity gives "mixed" (at most *Be careful*). |
| G4 (new) | Reassurance needs positive confirmation. |

**Explainability:** every report shows each signal's w, c and w·c, plus the formula with the final score ("How Asli decided").

**Uncertainty:**
- *Couldn't verify* is a first-class outcome: all 10 ambiguous messages and 4 of the 10 genuine ones landed there.
- Scam-pattern news is context, not proof (the hook rule).
- Absence of results is weak and can't establish high risk by itself.

**False-positive handling:** what the B1 investigation changed. **False negatives:** live recall is 10/10, but 6 of those are *Be careful*, not *High risk*. The Hindi job-fee scam scores 63, just under the 65 threshold. I didn't tune weights to one test message.

## 10. UX audit

- **Strongest:** the evidence-first report. Every flag opens to its sources, the Lens price cards are visual, absence claims link to the exact search, and the gauge plus "How Asli decided" make the score legible.
- **Weakest:** live latency. The free AI reader dominates: 23 s median, 65 s at the 90th percentile.
  - Mitigations already in place: the step-by-step timeline, a "free AI models can take ~30 s" hint, and now a live elapsed-time clock.
  - Cached examples are instant.
- **Fixed in this audit:** a keyboard-accessible screenshot button, report language for screen readers, placeholder contrast, mobile button row, eyebrow wrap, placeholder clipping and gauge label overflow.
- **Checked:**
  - No horizontal overflow at 320 and 375 px.
  - Keyboard focus brings marquee cards into view.
  - Clone cards are hidden from assistive technology.
  - `prefers-reduced-motion` disables all motion.
  - No console errors.

## 11. Performance audit (measured)

| Measure | Result |
|---|---|
| Page weight | HTML 10 KB + JS 43 KB + CSS 47 KB, no framework or build step |
| Cached or replayed check | 15 ms median, 147 ms at the 90th percentile (n = 88) |
| Uncached check (AI + search) | **23.3 s median, 64.9 s at the 90th percentile, 113.6 s maximum** (n = 54) |
| SerpApi latency (uncached, median) | Search 4.9 s, News 4.3 s, Jobs 17.0 s, Lens 18.4 s, Shopping 18.5 s |
| Pathological input | 4,000-character inputs: at most 25 ms of regex work (was 528 ms) |

## 12. Test results (actual)

| Suite | Result |
|---|---|
| Unit, integration and end-to-end (`uv run pytest`) | **256 passed**, 0 failed. Offline, no keys. |
| Fresh `git clone` + `uv sync --locked` + pytest | 256 passed (37 failed before fix A3) |
| Adversarial probes (`30`) | 8 reproduced before the fixes → **0** after |
| Evaluation, rules only | Scam recall 5/10, false alarms 0/10, ambiguous 10/10 |
| Evaluation, live | **Scam recall 10/10, false alarms 0/10**, confirmed 6/10, ambiguous 10/10 |
| Lint (`ruff`), JS syntax (`node --check`) | Clean |
| Dependency scan (`pip-audit`) | 0 known vulnerabilities |

## 13. Second audit (re-checked after the fixes)

- All 30 probes were re-run: 0 reproduce.
- The regression tests mirror probes that reproduced on the old code. The bank-alert and toll-free tests were also run against the pre-fix commit in a temporary worktree: they fail there and pass now.
- The fresh clone was re-run end to end, including `asli demo` over HTTP.
- The browser flow was re-checked through the new Host and CSRF middleware: an example ran to a report with no console errors.
- Access-token mode was re-checked after the middleware change: 401 without the token, then the cookie and the header both work.
- New-code edge cases:
  - Dotted UPI IDs in transaction notices stay intact through sentence splitting.
  - `.jobs` UPI IDs are no longer treated as links.
  - Toll-free 8-, 10- and 11-digit grouping is correct.
- **The second audit found 2 more issues,** C3 (`.jobs` UPI read as a website) and C4 (bill reminders unlocking pattern news). Both are fixed and tested.

## 14. Remaining risks

| Risk | Why it remains | Likelihood | Disclose? |
|---|---|---|---|
| Screenshot values are grounded against the AI's own transcription | No local OCR on free infrastructure | Medium for blurry screenshots | Yes (README limitations) |
| Weights are hand-set, and the evaluation set is small and self-written | No labelled corpus | High that the numbers would shift on real traffic | Yes (README) |
| Live latency of 23–65 s | Free OpenRouter models | Certain | Yes |
| Google results change over time, so replay recordings are snapshots | Inherent | Low for the demo | Yes (reports show "Recorded evidence · date") |
| Google Jobs queries in Hindi find little | The role and company are searched as written | Medium for Hindi job offers (low weight: W10 = 0.15) | In this report |
| No authentication by default | Local-first design | Low locally; high if deployed without a token | Yes (README environment variables) |
| API keys exposed in development chat | Already happened | Certain | **Rotate after the deadline** |

## 15. Hackathon judge view

| Criterion | Score | Reason |
|---|---:|---|
| Idea | 9 | Every Indian phone gets these messages, and the problem is obvious in five seconds |
| Originality | 8 | It checks the message's *claims* rather than classifying its wording: Lens prices, official contact pages, Maps for addresses, Jobs for offers |
| Technical complexity | 8 | Grounded extraction, a two-round planner, an evidence engine, a gated deterministic scorer, NDJSON streaming and replay. The audit adds trust-poisoning defences and measured evaluation. |
| Usefulness | 8 | Hindi and Hinglish, mobile, calm next steps (1930, Chakshu). Live latency costs a point. |
| SerpApi usage | 9 | Six engines, each essential. Without SerpApi, recall halves. |
| **Overall** | **8.5** | |

## 16. What stands between Asli and an obvious first place

1. **The submission isn't live yet.** The repository is still private and unpushed, and there's no demo video. *Fixable before the deadline: you push and record.*
2. **Live speed.** A first-time check takes 20–60 s on free models. *Partly fixable:* the demo uses cached examples, which are honest and instant, and the run view now shows a live clock. A paid or faster model would fix it properly, but that's outside the free-only constraint.
3. **The screenshot-to-Lens path hasn't been shown live with a real product screenshot.** The upload → Image API → Lens path is verified, and Lens pricing is verified with an image URL. *Fixable before submission:* record the demo with a mock product post, as `docs/DEMO.md` describes.

The highest-value improvement I could make safely was to harden the core differentiator itself: evidence you can trust. Four changes did that:
- The trust-poisoning fixes.
- No false alarms on genuine messages, measured live.
- Absence claims that link to the exact search.
- Honest, measured numbers in the README.

---

## 17. Follow-up: the screenshot → Lens path and speed (7 October, evening)

### The screenshot → Lens path

A mock Instagram-style post (a fictional seller, the Nike example's product photo and its scam caption) was uploaded through the API.

- **Bug found (P1): Lens never returned evidence for an uploaded screenshot.**
  - Lens on an upload takes 40–47 s, but Asli's Lens timeout was 40 s.
  - The retry came back with no results. Most likely it caught SerpApi's duplicate of the same search while it was still *processing*.
  - Asli then cached that empty response as "no results" for 24 hours.
  - All three upload-based Lens searches in the cache were empty. A direct diagnostic of the same image returned 59 matches.
  - **Fix:**
    - Lens timeout raised to 90 s and search phase to 110 s.
    - A response whose `search_metadata.status` isn't `Success` is a failure and is never cached.
    - The poisoned cache rows were removed.
  - Regression test: `test_a_search_still_processing_is_a_failure_not_cached_no_results`.
- **After the fix:**
  - Lens returned 59 matches in 14–17 s.
  - "Product photo appears on other shops" fires (38 sites).
  - Price evidence now comes from Lens itself: 83% below the ₹8,995 median of 14 listings.
  - Verdict: HIGH_RISK 92.

### Speed

| Change | Measurement | Result |
|---|---|---|
| Model "thinking" off for extraction (`ASLI_LLM_REASONING=off`) | Same message, Nemotron, reasoning low vs off (1 call each) | **22.2 s → 2.6 s**, 2,061 → 317 tokens, identical phone, link, organisation, scheme and actions |
| Same, vision (dots) | Mock product post, before vs after (1 read each) | AI read **68 s → about 13 s**, identical extracted claims and the same verdict and flags |
| Nemotron first for text | 46 of 49 live reads were already answered by Nemotron. Gemma answered once, in 41 s. | Skips a usually rate-limited first attempt |
| Number/link/UPI searches start while the AI reads | Simulation using delays drawn from 78 observed search latencies, 36 paired runs | Median 27.4 → 24.1 s, mean 34.4 → 30.8 s (about 10%) |

**Caveat:** the reasoning comparison is two calls, because the free tier allows 50 a day and the evaluation had used them. The 30-message evaluation must be re-run with reasoning off to confirm extraction quality before relying on it. `ASLI_LLM_REASONING=low` restores the previous behaviour.
