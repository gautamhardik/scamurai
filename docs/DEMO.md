# Demo video script (target 2:45, hard limit < 3:00)

The rules say the video must show the project **running locally**. Narration is optional, editing quality isn't judged, and the footage may be sped up.

## Setup (before recording)

1. `uv run asli serve` (live mode). The search cache is already warm for the examples, so they load instantly; the "cached" labels are honest.
2. Open http://127.0.0.1:8000 in a clean browser window at 1280×800. Zoom to 110% so text is readable.
3. Have ready: a **product screenshot** of a "₹1,499 Nike Air Jordan 1 Low" style post. A ready-made mock is at `demo-assets/mock-nike-post.png` (git-ignored: it embeds a retailer's product photo, so keep it out of the public repo). Its searches are cached until about 8 pm IST on 8 October (the AI read for 7 days), so until then it runs instantly: HIGH_RISK 92, with Lens finding the photo on Myntra and Nike India. Keep the Nike example chip as a fallback.
4. Close notifications. Use a screen recorder such as OBS or Xbox Game Bar (Win+Alt+R).

## Script

| Time | On screen | Say (or caption) |
|---|---|---|
| 0:00–0:12 | Home page. Hover the headline. | "Every Indian phone gets messages like these. Checking one properly takes 15 minutes. Asli checks the claims in seconds, with sources." |
| 0:12–0:45 | Click **Electricity bill SMS (Hindi)**. Show the timeline filling in: reading the Hindi screenshot → claims chips (number, `bijli-bill-pay[.]top`, ₹13) → Google Search / Google News checks. | "It reads a Hindi screenshot, pulls out the claims, then checks them live through SerpApi." |
| 0:45–1:05 | The report appears **in Hindi**. Open **समाचार / news** sources and click the Times of India article. | "High risk, explained in Hindi. Every flag has a source: here, newspapers reporting this exact scam." |
| 1:05–1:40 | Back. Click **Too-good-to-be-true deal** (or upload your product screenshot). Show the **Google Lens cards**: Myntra ₹6,297, Nike India ₹7,646, VegNonVeg ₹8,995. | "Google Lens finds the same photo on Myntra and Nike India at ₹6,000–9,000. The '₹1,499' deal is 83% below every real listing, and the shop's domain imitates Nike." |
| 1:40–2:05 | Click **“Digital arrest” threat (Hinglish)**. Show M9 *demands money under threat of arrest*, I7 *personal UPI ID*, and the news reports. | "The fastest-growing scam in India. Police and CBI never collect deposits over UPI. Asli says so in Hinglish." |
| 2:05–2:20 | Click **Genuine bank alert** → *No major warning signs*, with SBI's own contact page as the source. | "And when something is genuine, Asli shows the official confirmation instead of crying wolf." |
| 2:20–2:45 | Open **How Asli decided** on any report: the w · c table and formula. Optionally flash the README architecture diagram. | "The AI only reads. The verdict is transparent rules over SerpApi evidence: Google Search, News, Lens, Shopping, Jobs and Maps." |
| 2:45–2:55 | Home page. | "Asli doesn't guess from wording. It checks the claims." |

## Must be visible
- The browser address bar shows `127.0.0.1` (running locally).
- At least one **live** investigation timeline (checks ticking), not only finished reports.
- Clickable sources, the Lens price cards, and one Hindi or Hinglish report.
- The **How Asli decided** panel (shows the deterministic scoring).

## After recording
- Upload to YouTube as **Unlisted** (or Google Drive with "Anyone with the link").
- Open the link in an **incognito window** to confirm it plays without signing in.
- Check the length is **under 3:00**.
