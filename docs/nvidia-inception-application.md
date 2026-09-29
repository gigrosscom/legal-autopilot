# NVIDIA Inception — application draft (English)

> Pitch deck (English): https://claude.ai/artifact/28BuTXeCpWdW4yqyVb2ZN5 — download as PDF to upload.
> Fill the remaining `[[…]]` placeholders before submitting. Inception requires an **incorporated
> company** (ТОО in Kazakhstan or a Delaware C-corp), a working website on the company
> domain and a corporate email — apply from **info@konsilier.com**, not a personal mailbox.

---

## Company

- **Company name:** Konsilier AI LLP (ТОО «Konsilier AI»), BIN 260940036818
- **Registered address:** 222 Akseleu Seidimbek St., Kuramys microdistrict, Nauryzbay district, Almaty 050000, Kazakhstan
- **Website:** https://konsilier.com
- **Contact email:** info@konsilier.com
- **Country of incorporation:** Kazakhstan (registered 29 September 2026, Almaty; founder and sole participant: Nurlan Khabibulla)
- **Year founded:** 2026
- **Employees:** 1 (founder)
- **Funding stage:** [[Pre-seed / bootstrapped]]; total raised: [[$0]]
- **Industry:** Legal Tech / GovTech; AI for consumer legal self-help
- **Social:** Instagram, LinkedIn, Telegram, TikTok — @konsilier.ai

## One-line description (≤ 150 chars)

Konsilier.AI turns a person's everyday legal problem into a correct complaint, claim or
motion — and tells them exactly where and how to file it.

## Company description

Most people in Kazakhstan and Central Asia never defend their rights. A lawyer costs more
than the dispute, and official forms, deadlines and filing channels are hard to navigate.
Konsilier.AI closes that gap.

A user describes the problem in their own words, including slang, in Russian, Kazakh,
English, Turkish or Arabic. Examples: a faulty laptop from an electronics chain, an unpaid
salary, a fraudulent loan taken in their name, or a bank that refuses a refund. The
assistant then works through the case:

1. It identifies the legal situation and the competent body. Our registry covers the
   courts, police, prosecutors, regulators and ombudsmen.
2. It asks only for the missing facts and the evidence that matters: receipts,
   contracts, screenshots and ID. Users can photograph documents from the phone.
3. It drafts the document: pre-trial claim letter, complaint, application, statement of
   claim or motion. The draft follows the applicable statutes, with citations checked
   against official legal texts.
4. It gives step-by-step filing instructions for the real public channels (eOtinish, the
   court e-filing office, eGov, and official WhatsApp/Telegram lines of government bodies).
   Filing takes a few clicks, with e-signature where it is required.
5. It tracks deadlines and the authority's response, escalates when the response is
   late, and hands the case to a verified lawyer when self-service is not enough.

The product is live as a web app and an installable PWA (iOS/Android/desktop).

## Problem & market

- Consumer complaints in Kazakhstan reached about **83.8k in 2025 (+34% YoY)**
  [[confirm the source and figure before submitting]]. That is only the visible part:
  most people with a valid claim never file anything.
- Legal help is unaffordable for the typical dispute size ($100–$3,000).
- The state has digitized filing (eOtinish, e-courts, eGov), but citizens still don't know
  *what* to write, *to whom*, and *by when*.
- The same problem exists across Central Asia, the Caucasus and Turkey. The architecture
  is country-agnostic: each jurisdiction is a data pack (laws, bodies, templates) on one
  engine.

## Technology & AI usage

- **LLM core:** one switchable provider layer.
  - Anthropic Claude (direct API or Amazon Bedrock) and Google Gemini for drafting and
    classification.
  - Open-weight models (Qwen, Kimi) through OpenAI-compatible APIs (Cerebras, Groq,
    NVIDIA NIM) for the free consultation chat, tried in turn when one is overloaded.
  - We use strict JSON-schema structured outputs, so every model answer is validated
    before it reaches the user.
- **Grounding:** scenario packs plus a registry of legal forums and document types.
  Generation is constrained by statute references that are checked against official
  legal texts (a retrieval step over the legislation corpus).
- **Privacy by design:**
  - Personal data (names, national ID numbers, phones, addresses) is redacted before any
    LLM call and restored afterwards.
  - Identity documents are never sent to a model.
  - We host in-region (Kazakhstan).
- **Document pipeline:** templates rendered to DOCX/PDF, with e-signature (NCALayer) for
  channels that require it.
- **Stack:**
  - Python/FastAPI and PostgreSQL;
  - Next.js PWA;
  - containerized deploy on Yandex Cloud (KZ region).

## How we will use NVIDIA Inception

- **Cloud & inference credits:**
  - Evaluate open-weight models on GPU (NVIDIA NIM, Llama/Qwen/Mistral-class) for
    Kazakh- and Russian-language classification, PII detection and legal retrieval.
  - This reduces cost per case and lets sensitive steps run fully in-country.
- **NeMo / NIM:**
  - Fine-tune a small Kazakh/Russian model for intent classification and PII redaction.
  - Build a legal-domain embedding and reranking model for statute retrieval.
- **NeMo Guardrails:** add another safety layer for legal advice boundaries and emergencies
  (domestic violence, threats to life), which we currently route to hotlines.
- **Riva (ASR):** voice input for users who find it easier to speak than to write.
  Kazakh speech recognition is a strong accessibility win for older and rural users.
- **Deep Learning Institute:** training for the engineering team.
- **Go-to-market:**
  - Access to Inception VC Alliance for our seed round.
  - Co-marketing within the Central Asian AI ecosystem.

## Traction

- Live product: https://konsilier.com (web + installable app).
- [[N]] registered users, [[N]] cases opened, [[N]] documents generated,
  [[N]] filed, [[N]] resolved in the user's favour, [[₸ amount]] recovered.
  These numbers come from the admin panel: Admin → Metrics → CSV.
- Coverage: Kazakhstan, 20 legal situations with dedicated scenarios, plus a universal
  path for any complaint to a state body. Waitlist open for other countries.
- [[Pilots / partners / press, if any]]

## Business model

- The basic path is free: describe the problem, get the plan, file a simple complaint.
- Paid features:
  - a court-ready document package, with a fixed fee per document;
  - deadline tracking with escalation;
  - lawyer review.
- Lawyer marketplace: referral fee on cases handed to verified lawyers.
- B2B/B2G later: consumer-protection agencies, banks' complaint desks, employers' HR.

## Team

- **Nurlan Khabibulla** — Founder, developer, entrepreneur. Background in law, business and
  management; designed and built the product end to end. LinkedIn: [[url]]
- Legal advisors: [[licensed lawyers in Kazakhstan, if any]]

## Why now

- Frontier LLMs can finally write legally precise documents in Russian and Kazakh.
- Kazakhstan has one of the most digitized public-service stacks in the region, so
  filing can happen online end to end.
- We connect these two: AI drafting on top of the real digital filing channels.
