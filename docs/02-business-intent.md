# 02 — Business Intent

## 1. Why this business

Indian fashion e-commerce is large and growing, and buyers are price-sensitive and spread across many stores. Each store wants traffic and pays affiliates for it. An app that **sends ready-to-buy users to stores** sits in a natural money flow: we take no inventory, do no logistics and handle no returns.

## 2. Revenue model

| Stream | When | How it works |
|---|---|---|
| **Affiliate commission** (primary) | After v1, once affiliate accounts are approved | Every "Buy" button is an affiliate link. When the user buys within the store's attribution window, we earn a percentage. Rates vary by store and category (typically low single digits up to ~10% for fashion). |
| **Ads** (secondary) | Once there is steady traffic | Google AdMob: native ads in the trending feed and rewarded ads ("watch an ad for 2 extra try-ons"). Never in the core stylist flow. |
| **Premium** (future) | Once retention is proven | Unlimited try-ons, advanced Style DNA, early deal alerts. |

### Unit economics to track

- **Revenue per session** = store click-through rate × store conversion rate × average order value × commission rate
- **Cost per session** = AI tokens + try-on images + infrastructure (small on a homelab)
- **Goal:** revenue per session > cost per session. Every AI feature has a per-user quota and a global daily budget cap so costs can never run away (see the technical spec).

## 3. Competitive landscape

| Competitor | What they do | Our edge |
|---|---|---|
| ChatGPT / Gemini / Perplexity shopping | General AI product suggestions | Fashion-only, India-only, tap/swipe UI, remembers your taste, try-on, store comparison |
| Store AIs (Amazon Rufus, Myntra's assistant, etc.) | AI help inside one store | We compare **across** stores; they only show their own catalog |
| Price-comparison sites (BuyHatke, etc.) | Price tracking | We do discovery and styling, not just price |
| Instagram fashion pages | Inspiration | We turn inspiration into a purchase within budget ("shop from a photo") |

**Positioning:** *Your personal stylist that knows every store and respects your budget.*

## 4. Growth strategy

The product is designed so that using it spreads it:

1. **Ask friends polls.** Every poll is sent to 3–10 friends on WhatsApp. They vote on a web page and see an "Get your own stylist" call to action.
2. **Share a look.** Outfit cards made for Instagram stories, with the app link.
3. **Content.** Instagram Reels and Shorts such as "Full wedding look under ₹2,000", made from the app's own results.
4. **Seasonal moments.** Diwali, wedding season, summer, college fests: themed feeds and push campaigns.

## 5. Roadmap (business view)

| Phase | Goal | Exit signal |
|---|---|---|
| **Build v1** (mock data) | Full product experience working end to end | All v1 checkpoints done |
| **Closed testing** | 12+ testers for 14 days (a Play Store requirement for new personal accounts) and fix feedback | Testers complete sessions without help |
| **Affiliate applications** | Apply to Amazon Associates, Flipkart Affiliate, and Cuelinks/EarnKaro (for Myntra) together | Accounts approved |
| **Real data + launch** | Plug in real adapters and launch publicly on the Play Store | First affiliate earnings |
| **Growth** | Reels, polls and share loops | D7 retention ≥ 15%, rising DAU |
| **Monetize more** | Ads, then premium | Revenue per session > cost per session |

## 6. Key business risks

| Risk | Impact | Mitigation |
|---|---|---|
| Affiliate or API access denied or delayed | No real data or revenue | Apply to all of them plus affiliate networks; the adapter design lets us switch sources |
| Amazon's 3-sales rule within 180 days | Account closed | Apply only when the app is ready; first sales from friends and family |
| AI costs grow faster than revenue | Losses | Rule-based steps where possible, caching, quotas, a global budget cap, cheaper models per task |
| Try-on cost | Losses | Daily free limit; rewarded ads for extra try-ons later |
| Homelab downtime | Bad reviews | UPS, Cloudflare Tunnel, uptime alerts, off-site backups; plan a cloud move when traffic justifies it |
| Play Store policy rejection | Launch delay | Privacy policy, data safety form, account deletion, AI content reporting and affiliate disclosure built in from the start |
| Users prefer ChatGPT | Low adoption | Differentiate on try-on, store comparison, memory and the swipe experience |

## 7. Business metrics (shown in the admin dashboard)

- DAU, WAU, D1/D7/D30 retention
- Sessions per user; time to first liked product
- Store click-through rate (CTR) per store
- Wishlist saves, polls created, poll votes, shares
- Try-ons per user; try-on → store click rate
- AI cost per session, per user and per feature
- Later: affiliate revenue per store and revenue per session
