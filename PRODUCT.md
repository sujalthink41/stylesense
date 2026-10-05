# Product

<!-- impeccable:product-schema 1 -->

## Platform

android

One custom StyleSense design language, identical on Android and iOS (confirmed). Android (Play Store) ships first; iOS later from the same codebase. Honor platform affordances (system back, edge-to-edge, safe areas), not platform styling.

## Stack

React Native with Expo (TypeScript), confirmed by the owner. Talks to the StyleSense FastAPI backend in `backend/` (REST + Server-Sent Events). Screens are server-driven through the generative-UI component catalog (`backend/contracts/genui.schema.json`, catalog v2).

## Users

- **Primary:** 18–30 year olds in India: college students and young professionals, budget-conscious (₹300–₹3,000 per item), shopping online at least monthly, living on Instagram and WhatsApp. Usually on a mid-range Android phone, often one-handed, often on patchy mobile data.
- **Secondary:** anyone dressing for an event (wedding, party, trip, festival) who wants a complete outfit under one total budget.
- **Job:** "Find me something that suits me, for this occasion, within my budget, at the best price, without opening four shopping apps."

## Product Purpose

An AI fashion stylist that finds the best clothes for your budget across Amazon, Flipkart and Myntra, mostly through taps and swipes, not typing. Success (v1): first liked product in under 60 seconds; at least 40% of sessions end in a store click or a wishlist save; D7 retention ≥ 15%.

## Positioning

A stylist that shops, not a chatbot that talks. The AI answers with interface (chips, sliders, swipe decks, comparisons), never paragraphs; it remembers your taste from every swipe; it compares the same item across Indian stores and keeps every pick inside your budget. General chatbots can't remember you, compare Indian stores side by side, or show the item on you.

## Operating Context

- Entry: an occasion tile (party, wedding, office…), a quick search, or a photo of a look.
- 1–3 tap questions (category, who it's for, budget) → a swipe deck of picks, each with short "why this pick" chips.
- Card → product detail: store-by-store prices with the best one flagged, similar picks, "complete the look" within a whole-look budget, virtual try-on on your own selfie.
- Save to a wishlist or outfit boards; share a look as a link; ask friends to vote in a poll (they vote on the web, no install).
- Style DNA onboarding: about 30 seconds, taps only.
- Buying happens on the store's site through a tracked link.

## Capabilities and Constraints

- Every screen is rendered from server-sent components; the app is a renderer of a fixed, versioned catalog (14 types in v2). Unknown components degrade to an "update the app" banner.
- Works with no AI configured: rules drive questions, ranking and reasons; AI only enriches.
- v1 catalog is mock data (~300 products, fictional brands, placeholder PNG images); real store APIs come later without app changes.
- User photos are private, signed URLs, deleted after 24 h. Try-on is 3 per day; photo search 10 per day.
- Prices are integer paise, shown as ₹ with Indian digit grouping (₹1,499; ₹1,00,000).
- Sign-in: Google only.
- Out of v1: price history, wardrobe scan, voice, phone OTP, ads, iOS release.

## Brand Commitments

- Name: **StyleSense** (final). No existing logo, colours or typography: the brand identity is designed from scratch.
- The owner asked for a very modern, professional, classy look (binding).
- Copy language: English only in v1; Indian conventions for currency and numbers.

## Evidence on Hand

No testimonials, user counts, press, ratings or partnerships exist. Product imagery is placeholder. Future work must not fabricate any of them.

## Product Principles

1. **Tap first, type optional.** Every screen offers tappable options; typing is never required.
2. **UI, not paragraphs.** The stylist speaks in components, not text blocks.
3. **Budget is sacred.** Never show an item outside the user's budget unless they ask.
4. **Honest by default.** Reasons come from real product attributes; affiliate links are disclosed; nothing is invented.
5. **Fast on a mid-range phone.** First products visible within seconds of the first tap.

## Accessibility & Inclusion

Mid-range Android devices and patchy networks are the norm, so design for small screens, large text settings, one-handed reach, and graceful loading/offline states. Inclusive of all genders (men, women, unisex, "no preference").
