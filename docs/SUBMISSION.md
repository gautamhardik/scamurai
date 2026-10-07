# Submission form answers (paste-ready)

## Project name
Asli

## One-line description
Asli checks suspicious messages, screenshots, links and numbers against live web evidence from SerpApi, and returns a source-cited risk report in English, Hindi or Hinglish.

## Project description
Indians receive a steady stream of fake electricity-bill SMSes, KYC links, "digital arrest" threats, fake customer-care numbers, too-good-to-be-true deals and job offers that ask for a fee. Checking one properly takes about 15 minutes of searching, so most people don't check.

Asli does that checking for them. You paste or screenshot the message. Asli extracts the claims it makes (who it says it's from, the number, link, UPI ID, price, job, address), plans only the searches that matter, and checks each claim live through SerpApi: Google Search, News, Lens (with the Image API), Shopping, Jobs and Maps.

A transparent, deterministic risk engine (not the AI) weighs the evidence. The result is a calm report: a verdict, a confidence level, every warning linked to its source, and what to do next (1930, cybercrime.gov.in, Chakshu). Reports come in English, Hindi or Hinglish, matching the message.

**Who it's for:** anyone in India with a phone, and especially people who check messages on behalf of elderly relatives.

## Track
Knowledge & Public Interest

## SerpApi usage (APIs and why they matter)
SerpApi is Asli's evidence layer. Without it, Asli could only guess from a message's wording. Each engine answers one question about a claim:

- **Google Search:**
  - Finds the official website and contacts of the organisation the message claims to be (knowledge graph and top results).
  - Searches the exact phone number, UPI ID or domain for scam and complaint reports.
  - Runs a `site:` search to check whether the official site lists the number on a contact page.
- **Google News:** checks whether this kind of message has been reported as a scam (e.g. "electricity bill disconnection SMS scam", "digital arrest scam"), and counts independent outlets.
- **Image API + Google Lens:** uploads the screenshot or product photo to find where else it appears and at what price. This catches deals that reuse photos from Myntra or Nike India at 80% below the real price.
- **Google Shopping:** the fallback for the real price of the product when Lens finds too few prices.
- **Google Jobs:** checks whether the company is actually hiring for the role in a job offer.
- **Google Maps:** checks whether the "office" address in a job offer belongs to the company, or to apartments and hotels.

Asli uses the official `serpapi` Python SDK. Every search is cached by engine and normalized parameters. Each investigation is limited to 8 searches in 2 rounds, with daily and credit-reserve guards. The 10 demo scenarios replay from recorded real SerpApi responses, so judges can run them without a key.

## Did the project exist before the hackathon?
No. It was started on 7 October 2026 for this hackathon. The git history shows the build.

## AI tools used
- **Building it:** Claude Code (Anthropic Claude Opus 5.5) was used for architecture, code, tests and documentation. Hardik Gautam directed and reviewed the work.
- **At runtime:** free models on OpenRouter (Google Gemma 4, NVIDIA Nemotron, dots.3) read messages and screenshots and extract claims. All risk scoring is deterministic code, and the model never decides the verdict.

## Links
- Repository: https://github.com/gautamhardik/asli
- Demo video: _(unlisted YouTube link; test in incognito)_

## Checklist before pressing Submit
- [ ] The repository is **public**, and the README renders with screenshots
- [ ] The CI badge is green
- [ ] The video is under 3:00 and opens in incognito
- [ ] The lead participant details are filled in (you must be 18+ and resident in India)
- [ ] Community affiliation is selected if you belong to a partner community (BangPypers, HydPy, TriPy, AI Geeks Chennai, PyDelhi)
- [ ] The Rules and Terms are accepted
- [ ] **Submit project** is clicked (a saved draft does not count)
- [ ] After the deadline, regenerate both API keys (they were shared in a chat)
