# 01 — Product Overview

> **StyleSense** (working name) — an AI fashion stylist app for India that finds the best clothes for your budget across stores, mostly through taps and swipes, not typing.

## 1. One-line pitch

**"Tinder for fashion, with a personal AI stylist that shops Amazon, Flipkart and Myntra for you."**

## 2. The problem

Buying clothes online in India today means:

- Opening 3–4 apps (Amazon, Flipkart, Myntra, Ajio) and searching each one separately.
- Scrolling through hundreds of results, most of them irrelevant or outside budget.
- Not knowing whether something will suit you (fit, color, skin tone, occasion).
- Not knowing which store has the best price for the same or similar item.

General AI chatbots (ChatGPT, Gemini) can suggest products, but they are text-heavy, forget you between sessions, don't compare Indian stores side by side, and can't show you wearing the item.

## 3. The solution

A mobile app where the user:

1. **Taps an intent**: an occasion tile, a quick search or a photo of a look they like.
2. **Answers 3–4 quick questions by tapping chips**: budget, size, fit, style.
3. **Swipes through hand-picked products**: right = like, left = skip. The app learns their taste with every swipe.
4. **Sees, for each product**: price comparison across stores, a one-line "why this pick", a virtual try-on on their own photo, and matching items to complete the look.
5. **Buys on the store** through a link (later an affiliate link, which is how we earn).

## 4. Core product principles

| Principle | What it means in practice |
|---|---|
| **Tap first, type optional** | Every screen offers tappable options. Typing or voice is always available but never required. |
| **UI, not paragraphs** | The AI never answers with text blocks. It responds with UI components: chips, cards, sliders, comparisons. This is called *generative UI*. |
| **Personal by default** | Style DNA + swipe history make every result personal. The app remembers you; a chatbot does not. |
| **Budget is sacred** | Never show items outside the user's budget unless they ask. |
| **Fast** | First products are visible in under 5 seconds from the first tap. |
| **Honest** | We clearly disclose affiliate links. "Why this pick" is based on real product attributes, never invented. |

## 5. Target users

- **Primary:** 18–30 year olds in India, college students and young professionals, budget-conscious (₹300–₹3,000 per item), shop online at least monthly, active on Instagram and WhatsApp.
- **Secondary:** anyone shopping for an event (wedding, party, trip, festival) who wants a complete outfit under a total budget.

## 6. Version 1 feature list

| # | Feature | Summary |
|---|---|---|
| F1 | **AI Stylist (generative UI)** | Intent → 3–4 chip questions → curated results, all as interactive components. |
| F2 | **Style DNA** | 30-second tap-only onboarding: gender/fit preference, body type, skin tone, sizes, favorite styles. |
| F3 | **Swipe discovery** | Full-screen product cards; swipes train a personal taste profile. |
| F4 | **Store comparison** | Same or similar product across Amazon, Flipkart and Myntra with the best price highlighted. |
| F5 | **Why this pick** | A one-line, attribute-based reason for each recommendation. |
| F6 | **Complete the look** | Matching items for the selected product within the remaining budget. |
| F7 | **Shop from a photo** | Upload a look and get similar items under budget. |
| F8 | **Virtual try-on** | See the item on your own photo (daily free limit). |
| F9 | **Wishlist & outfit boards** | Save items and group them into outfits. |
| F10 | **Share a look** | A beautiful outfit card for Instagram stories and WhatsApp, with an app link. |
| F11 | **Ask friends** | A shareable poll ("which one?"). Friends vote on a web page without installing the app. |
| F12 | **Trending feed** | A daily curated feed ("Trending under ₹500", season and festival edits). |
| F13 | **Price-drop alerts** | Push notifications when a wishlisted item gets cheaper. |
| F14 | **Account & privacy** | Google sign-in, data export, in-app and web account deletion. |

**Explicitly out of v1:** price-history charts and "buy now or wait", wardrobe scan, Hinglish voice, phone OTP login, ads, iOS release (the code supports iOS; only the release is deferred).

## 7. Data in v1

V1 runs on a **realistic mock catalog** (~300 products across the three stores). Real store integrations (Amazon PA-API, Flipkart Affiliate API, Myntra through an affiliate network) are added after v1 is complete, through pluggable *product source adapters*. The app does not change when real data arrives.

## 8. Platforms

- **Mobile app:** Android (Play Store) first. iOS later from the same codebase.
- **Admin dashboard:** web, internal only.
- **Public web pages:** poll voting page, share-a-look landing page, account deletion page, privacy policy.

## 9. What success looks like (v1)

- A new user reaches their first liked product in **under 60 seconds**.
- **At least 40%** of sessions end with a store click or a wishlist save.
- **D7 retention of 15% or more.**
- **AI cost per session** under a set budget (tracked in the admin dashboard).
