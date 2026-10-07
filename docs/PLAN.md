# Asli — Master Plan (approved 2026-10-07)

> Approved decisions: GitHub account **gautamhardik** · LLM option **(c)** shared free OpenRouter pool · submit by **Sat 10 Oct 2026, 16:00 IST** (deadline 23:59 IST) · feature freeze **Fri 9 Oct, 21:00 IST**.

## 1. Executive summary

Asli is a local-first web app (FastAPI + static HTML/CSS/vanilla JS). A user submits text, a screenshot, a link or a phone number.

1. An OpenRouter free vision model extracts a **grounded claim graph** (every phone/URL/email/amount must appear verbatim in the input or the screenshot transcript).
2. A deterministic **planner** turns the claim graph into ≤8 SerpApi searches across 6 engines (+ the free Image API) in ≤2 rounds. The LLM never writes queries.
3. An **evidence engine** normalizes, deduplicates, classifies and ranks results; **checks** convert evidence into signals.
4. A deterministic **risk engine** (noisy-OR + gates + coverage-based confidence) yields HIGH_RISK / SUSPICIOUS / LOW_RISK / UNVERIFIED. The LLM never scores.
5. A **report** where every flag cites ≥1 source, with template-based headline and recommendations in English / Hindi / Hinglish.

**Replay mode** serves real recorded SerpApi responses + LLM extractions so the demo is deterministic and judges can run it without keys.

## 2. Audit findings (2026-10-07)

- Empty project; tooling: Python 3.12 via uv, git, gh (gautamhardik), Node not used.
- SerpApi Free plan: 250/month (248 after probes), 250/hour.
- OpenRouter free tier: 50 free-model requests/day; failed (429) requests don't count.
- Google Shopping (gl=in): ₹ prices, but product variants pollute the median → title-similarity + IQR filter.
- Google Lens (country=in) on a product photo: priced visual matches from Myntra ₹6,297 / Nike India ₹7,646 / VegNonVeg ₹8,995 → **Lens is the primary price baseline**.
- SerpApi Image API: `POST /image`, field `image`, ≤500 KB, image_id expires in 10 min, **0 credits**.
- `google/gemma-4-31b-it:free` → 429 (upstream shared pool); `thinkingmachines/inkling:free` → 403; `dots-studio/dots-3-note-preview:free` works with `reasoning.effort=low` (perfect Hindi OCR, flagged injection, ~47 s; needs `max_tokens≥3000`).
- LLM-written search queries are unsafe (it appended "AI prompt injection…") → **closed scheme enum + curated query templates**.

## 3. Product

- **Problem:** fake KYC / electricity / courier / digital-arrest messages, fake customer-care numbers, fake Instagram deals, fee-charging job offers. Verifying one takes 15+ minutes of searching.
- **Insight:** *scammers reuse scripts, numbers, photos, domains and addresses — every reuse leaves a trace on the web.* Asli checks claims instead of judging wording.
- **Non-goals:** blocking, crowdsourced number DB, legal determinations, "100% scam".

## 4. Stack (final)

Python 3.12 (uv) · FastAPI + Uvicorn (NDJSON streaming) · static HTML/CSS/vanilla JS served by FastAPI (no build) · official `serpapi` SDK (+ its `upload_image`) wrapped in `asyncio.to_thread` · httpx for OpenRouter · pydantic v2 / pydantic-settings · pillow · phonenumbers · tldextract (bundled snapshot, no network) · rapidfuzz · SQLite (stdlib, WAL) · pytest + ruff · GitHub Actions (ubuntu + windows). Local-first; no public hosting.

## 5. SerpApi matrix

| Engine | Question | Query | Signals |
|---|---|---|---|
| `google` (org) | What is the official domain/contact? | `"{org}" official website` (skipped if curated) | official domain → I2, T2, W5 |
| `google` (phone) | Is this exact number reported? | `"{10d}" OR "{5 5}" OR "+91 {5 5}"` | W1 |
| `google` (domain) | Is this domain reported / does it exist? | `"{etld1}"` | W2, W4 |
| `google` (round 2) | Does the official site list this number? | `site:{official} "{10d}"` | T1 / W3 |
| `google_news` | Has this script been reported? | curated template per scheme | W6, W7 |
| Image API | Upload screenshot for Lens | `POST /image` (0 credits) | — |
| `google_lens` | Where else does this photo appear, at what price? | image_id or url, `country=in` | W8, W9, T5 |
| `google_shopping` | What does the product really cost? | `{brand} {product}` (round 2 if Lens < 3 prices) | W8, T5 |
| `google_jobs` | Does this role at this company exist? | `{role} {company}` | T3, W10 |
| `google_maps` | Is the company at this address? | address or `{company} {city}` | T4, W11 |

## 6. Agent limits

≤8 searches/investigation · ≤2 rounds · 4 concurrent searches · 25 s per search (Lens 40 s) · 1 retry on network/5xx/timeout · no retry on 401/429 · 75 s investigation budget · 1 LLM call per investigation (vision chain gemma-31b → gemma-26b → dots; text chain gemma-31b → nemotron-super → dots) · regex-only fallback · daily search cap 80 · credit reserve 10.

Cache: SQLite, key = sha256(engine + canonical params minus api_key), q normalized (NFKC, lower, collapsed spaces); Lens keyed by image sha256 / image URL. TTL: google 24 h, news 12 h, shopping 24 h, lens 24 h, jobs 24 h, maps 7 d.

## 7. Risk engine

R = 1 − Π(1 − w·c) over risk signals; T = 1 − Π(1 − v·c) over trust signals; score = round(100 · R · (1 − 0.75·T)).

| ID | Signal | w | c |
|---|---|---|---|
| I1 | brand_lookalike_domain | .60 | .95 curated / .85 KG |
| I2 | official_domain_mismatch | .45 | .85 KG / .70 top organic |
| I3 | authority_unofficial_domain | .40 | .75 |
| I4 | free_email_corporate | .35 | .95 |
| I5 | punycode_homograph | .50 | .90 |
| W1 | phone_reported | .60 | 1 src .60 · 2 .80 · ≥3 .95 |
| W2 | domain_reported | .60 | same |
| W3 | official_contact_mismatch | .30 | .75 |
| W4 | domain_no_footprint | .20 | .70 |
| W5 | company_no_footprint | .35 | .70 |
| W6 | known_scam_pattern | .35 | .70 (2) / .85 (≥3) |
| W7 | org_impersonation_reports | .15 | .70 |
| W8 | price_anomaly | .50 (<40%) / .65 (<20%) | .90 / .75 |
| W9 | image_reused | .30 | .80 |
| W10 | job_not_listed | .15 | .60 |
| W11 | address_mismatch | .30 | .70 / .50 |
| M1 | credential_request (critical) | .65 | .95 |
| M2 | upfront_fee (critical) | .60 | .90 |
| M3 | threat_or_urgency | .15 | .90 |
| M4 | payment_request | .20 / .25 personal UPI | .90 |
| M5 | ai_injection_text | .30 | .90 |
| M6 | suspicious_tld | .15 | .90 |
| M7 | url_shortener | .10 | .95 |
| M8 | too_good_to_be_true | .25 | .70 |
| T1 | phone_on_official_site | .75 | .90 |
| T2 | domain_official | .70 | .90 / .80 |
| T3 | job_listing_match | .40 | .80 |
| T4 | maps_business_match | .25 | .70 |
| T5 | price_plausible | .15 | .80 |

Gates: **G1** HIGH needs an identity/web signal with c ≥ .6 and w·c ≥ .25, or a critical signal. **G2** no identity/web and no critical → score ≤ 55. **G3** trust (T1/T2, v·c ≥ .5) + risk (W1/W2/I1/I2) on the same entity → ≤ SUSPICIOUS, "Mixed evidence", confidence low.

Levels: HIGH_RISK ≥ 65 (+G1, not G3) · SUSPICIOUS 35–64 · LOW_RISK < 35 with coverage ≥ .6, ≥1 verifiable entity and a trust signal or ≥2 checks with results · UNVERIFIED otherwise.

Confidence: high = coverage ≥ .8 and ≥2 independent sites (or deterministic identity c ≥ .85) and no contradiction · medium = coverage ≥ .5 · low otherwise. The score is shown only in "How Asli decided" as risk points, never as a probability.

## 8. Evidence engine

Normalize → classify source (official, government, news, complaint_forum, registry, marketplace, job_board, social, …) → canonical URL + dedupe (same eTLD+1 + similar title) → entity & lexicon match (EN + HI) in the *same* item → relevance = .45 entity + .25 lexicon + .15 source + .10 rank + .05 recency. Citation invariant: every flag cites ≥1 evidence id; identity/web flags cite ≥1 web item; violators are dropped and logged. Links to domains from the message are rendered defanged and non-clickable.

## 9. Security

Keys as SecretStr, never sent to the browser; redaction filter for `api_key=` / `sk-or-` in logs and exception text; server never fetches user URLs (only serpapi.com + openrouter.ai); uploads ≤5 MB, magic-byte sniff (PNG/JPEG/WebP), 40 MP limit, re-encode (strips EXIF); untrusted-content delimiters, JSON-only closed-enum LLM output, grounded entities only reach queries; `textContent` rendering; strict CSP; bind 127.0.0.1; per-IP rate limit + 2 concurrent; PII redaction (cards/Aadhaar/PAN/OTP) before the LLM; logs never contain message text.

## 10. Priorities

- **P0:** text + screenshot (+ link/phone) input · extraction + grounding + regex fallback · planner · google/news/lens+Image API/shopping/jobs/maps · cache/budget/replay · evidence + risk engines · 4 MVP scam types · streaming UI + report + evidence drawers + error states · en/hi/hinglish templates · security · tests + CI · README · video · submission.
- **P1:** Lens price cards · copy summary · report reload endpoint · `asli doctor` · credits indicator · language switch · LLM bbox crop · curated official domains.
- **P2:** loan apps (google_play) · LLM narrative · stats · entity confirmation · dark mode.
- **CUT:** Telegram/WhatsApp bot, hosting, Next.js, auth, Postgres/Redis/Docker, URL fetching/expansion, WHOIS/carrier APIs, local OCR, ML training, RAG, Playwright.

## 11. Schedule (IST)

| When | Phase |
|---|---|
| Wed 15:00–16:30 | 1 Foundation |
| Wed 16:30–19:30 | 3 SerpApi integration |
| Wed 20:00–23:00 | 2 Core investigation (ingest, regex, LLM extraction) |
| Thu 09:00–12:00 | 4 Evidence engine + checks + planner |
| Thu 12:00–20:00 | 5 Risk engine, orchestrator, API, live calibration + recordings |
| Thu 20:00–22:00 | 7a Tests + CI |
| Fri 09:00–15:00 | 6 UX |
| Fri 15:00–18:00 | 7b QA · 8 fresh-clone packaging |
| Fri 18:00–21:00 | 9 Demo prep — **feature freeze 21:00** |
| Sat 09:00–16:00 | README, video (user), **submit by 16:00** |

## 12. E2E scenarios

| # | Scenario | Expected | Must include | Must not include |
|---|---|---|---|---|
| 1 | Electricity SMS screenshot (HI) | HIGH_RISK | I3, W6, M3, M4 | T* |
| 2 | Fake customer-care number | ≥ SUSPICIOUS | W3 or W1 | T1 |
| 3 | Nike Air Jordan 1 Low ₹1,499 | HIGH_RISK | W8, W9 | T5 |
| 4 | Job offer, Gmail + fee | HIGH_RISK | M2, I4 | T3 |
| 5 | Genuine SBI alert | LOW_RISK | T1 | W1, I1, I2 |
| 6 | "Is this Rahul? reply YES" | UNVERIFIED | — | HIGH_RISK |
| 7 | AI-injection screenshot | ≥ SUSPICIOUS | M5 | changed extraction |

## Implementation log

- 2026-10-07: plan approved; repo initialised; recordings/scenarios live under `src/asli/demo/` so they ship with the package.
- 2026-10-07 (build loop, day 0): core pipeline, web UI, 10 recorded scenarios, 224 tests, CI. Changes vs plan:
  search-phase budget 90 s and LLM timeout 120 s (free models are slow); Google Jobs timeout 60 s;
  narration is template-only (1 LLM call per investigation); added signals I6 helpline_is_mobile,
  I7 authority_personal_upi, W12 upi_reported, M9 extortion_threat; reports from arbitrary pages
  (not complaint/news/government) cap at c=0.5; `.bank.in` recognised as bank-official; official-number
  check requires a contact/help page; Lens prices filtered to the same product variant.
