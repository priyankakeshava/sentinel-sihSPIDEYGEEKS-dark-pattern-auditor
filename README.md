# SENTINEL — Government Dark Pattern Auditor

> An automated, evidence-based regulatory auditing system that executes complete web journeys, detects manipulative interface practices, verifies suspicious behaviour through replay, and presents evidence for human regulatory review.

## Overview

Online platforms can use interface practices that influence users into making purchases, subscriptions, payments, or decisions they may not have intended.

Traditional inspection often focuses on individual screens or static webpages. **SENTINEL** takes a journey-based approach.

Instead of analysing a single screen, SENTINEL executes and observes a complete user journey:

**Search → Product → Cart → Review → Checkout**

During the journey, the system records browser states, screenshots, prices, cart changes, interactions, timers, and other observable UI changes.

The captured evidence is then analysed for dark patterns, stored for investigation, and replayed where behavioural verification is required.

## Core Workflow

```text
                    START
                      │
                      ▼
              Target Website
                      │
                      ▼
             Automated Journey
                      │
                      ▼
       Search → Product → Cart
                      │
                      ▼
              Review → Checkout
                      │
                      ▼
       Capture State + Screenshots
                      │
                      ▼
             Evidence Graph
                      │
                      ▼
             Hybrid Detection
                 /         \
                /           \
        Rule-based         NLP / ML
        Behaviour          Analysis
                \           /
                 \         /
                  ▼       ▼
                  Findings
                     │
                     ▼
            Behavioural Replay
                     │
                     ▼
              Evidence Report
                     │
                     ▼
          Investigation Console
                     │
                     ▼
            Human Regulatory Review
                     │
                     ▼
                    END
```

## What SENTINEL Does

### 1. Journey-Based Auditing

SENTINEL uses Playwright to execute a complete browser journey rather than analysing an isolated webpage.

The prototype captures:

- Page transitions
- Screenshots
- Browser state
- Prices
- Cart contents
- User interactions
- UI states
- Timer behaviour
- Checkout state

This allows the system to identify changes that may only become visible when multiple pages or actions are considered together.

### 2. Journey Evidence Graph

SENTINEL connects actions, state changes, observations, and findings across the complete journey.

```text
User Action
     ↓
Browser State
     ↓
State Change
     ↓
Captured Evidence
     ↓
Detection
     ↓
Finding
```

### 3. Hybrid Detection

SENTINEL combines deterministic browser-state analysis with language analysis.

**Rule and Behaviour-Based Detection**

Objective behaviours can be tested directly from the browser, including:

- Optional items appearing in the cart
- Additional charges appearing later
- Suspicious countdown behaviour
- Payment actions blocked by unrelated consent requirements

**NLP / ML Detection**

Language-based manipulation requires semantic analysis.

The ML component is being developed for patterns such as **Confirm Shaming**, where the meaning and tone of a decline option are important.

The planned multilingual NLP layer uses **XLM-R** and will be evaluated independently before being integrated into the stable detection pipeline.

## Dark Pattern Detectors

The current prototype demonstrates five categories.

### Basket Sneaking

Detects cases where an optional item or service appears in the cart without explicit user consent.

### Drip Pricing

Detects additional charges or price changes introduced during the purchasing journey.

### Confirm Shaming

Identifies decline options containing guilt-oriented, loss-oriented, or manipulative language.

The current stable MVP uses a prototype language heuristic. A multilingual XLM-R-based semantic classifier is being developed as the ML extension for this category.

### False Urgency

Detects suspicious countdown behaviour and verifies it through a fresh browser session.

```text
Observe Timer
     ↓
Wait / Re-check
     ↓
Fresh Browser Session
     ↓
Repeat Observation
     ↓
Compare Behaviour
     ↓
Reproduced?
```

### Forced Action

Detects cases where an unrelated action or consent requirement blocks the user from continuing.

## Behavioural Verification

SENTINEL does not rely only on a single observation when a behaviour can be tested dynamically.

Suspicious behaviour can be replayed in a fresh browser context.

This allows the system to ask:

> **Can the observed behaviour be reproduced independently?**

The replay result becomes part of the evidence associated with the finding.

## Evidence Collection

SENTINEL is designed around evidence rather than prediction alone.

The prototype records:

- Screenshots
- Journey steps
- Browser state
- Cart state
- Price information
- Detection results
- Replay results
- Evidence metadata
- SHA-256 hashes
- Human review status

Captured screenshots are hashed using SHA-256 to provide an integrity identifier for evidence artefacts.

## Human-in-the-Loop Investigation

SENTINEL does not make an autonomous legal determination.

```text
Automated Detection
        ↓
Evidence
        ↓
Finding
        ↓
Human Investigation
       / \
      /   \
 Confirm  Reject
```

The investigation console allows a reviewer to inspect the evidence and confirm or reject a finding.

## Controlled Demonstration Environment

The repository contains **DarkShop**, a controlled demonstration commerce website.

**Manipulative Mode** contains known behaviours designed to exercise the SENTINEL detectors.

**Clean Control Mode** provides a control journey without the targeted manipulative behaviours.

This makes the prototype reproducible during demonstrations and validation without depending on a changing third-party website.

## System Architecture

```text
┌───────────────────────────┐
│         DarkShop          │
│   Controlled Web Store    │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│        Playwright         │
│   Automated Web Journey   │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│          FastAPI          │
│ Audit + Detection + Replay│
└─────────────┬─────────────┘
              │
       ┌──────┴──────┐
       ▼             ▼
┌────────────┐ ┌────────────────┐
│   MySQL    │ │ Evidence Store │
│ Audit Data │ │ Screenshots    │
└────────────┘ └────────────────┘
              │
              ▼
┌───────────────────────────┐
│   Investigation Console   │
│      React / Next.js      │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│   Human Regulatory Review │
└───────────────────────────┘
```

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Browser Automation | Playwright | Executes isolated browser journeys |
| Backend | Python + FastAPI | Audit orchestration, detection, replay and APIs |
| Database | MySQL | Stores audits, journey steps, findings and replay results |
| Frontend | React / Next.js | Investigation console |
| Controlled Website | Node.js | DarkShop demonstration environment |
| Evidence Integrity | SHA-256 | Evidence hashing |
| NLP / ML | XLM-R | Multilingual semantic detection extension |
| Containerization | Docker Compose | Reproducible multi-service deployment |

## Project Structure

```text
SENTINEL/
│
├── backend/
│   ├── main.py
│   └── requirements.txt
│
├── darkshop/
│   ├── server.js
│   ├── package.json
│   └── ...
│
├── frontend/
│   ├── src/
│   ├── package.json
│   └── ...
│
├── data/
│   └── evidence/
│
├── DEMO_SCRIPT.md
├── FUTURE_SCOPE.md
├── MYSQL_SETUP.md
├── TECH_STACK.md
├── VALIDATION_CHECKLIST.md
├── docker-compose.yml
├── Dockerfile.backend
├── run-windows.bat
├── run-mac-linux.sh
└── LICENSE
```

## Installation and Running

SENTINEL can be run locally without Docker.

### Prerequisites

Install:

- Python 3.11+
- Node.js
- npm
- MySQL for the intended database configuration

A SQLite fallback is available for local development when MySQL is unavailable.

### Local Development

**1. Start DarkShop**

```bash
cd darkshop
npm install
npm start
```

DarkShop will be available at:

```text
http://127.0.0.1:9000
```

**2. Start the Backend**

From the project root:

```bash
.venv\Scripts\activate
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

The FastAPI backend will be available at:

```text
http://127.0.0.1:8000
```

**3. Start the Investigation Console**

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

## Docker Deployment

If Docker and Docker Compose are available:

```bash
docker compose up --build
```

The Compose configuration is designed to run:

```text
MySQL
   +
DarkShop
   +
FastAPI / Playwright Backend
   +
Investigation Console
```

## Recommended Demonstration

1. Click **Run Manipulative Audit**.
2. Show the Search → Product → Cart → Review → Checkout journey.
3. Show captured screenshots and browser-state evidence.
4. Open the detected findings.
5. Demonstrate the False Urgency fresh-session replay.
6. Show the Evidence Graph.
7. Confirm or reject a finding.
8. Run the Clean Control journey and compare the findings.

## Validation

The repository includes a validation checklist covering:

- Complete journey execution
- Screenshot capture
- Browser-state capture
- Basket Sneaking
- Drip Pricing
- Confirm Shaming
- False Urgency
- Forced Action
- Replay verification
- SHA-256 evidence hashing
- Clean-control behaviour
- Human review

See `VALIDATION_CHECKLIST.md`.

## AI / ML Development

The SENTINEL architecture includes a multilingual NLP layer for language-based dark patterns.

The development path is:

```text
Multilingual Dataset
        ↓
Train / Validation / Test Split
        ↓
XLM-R
        ↓
Fine-Tuning
        ↓
Held-Out Evaluation
        ↓
Error Analysis
        ↓
Semantic Classification
        ↓
Sentinel Evidence Pipeline
```

The initial focus is **Confirm Shaming**, because it depends on the semantic meaning and tone of language rather than only on observable browser state.

The ML component is evaluated separately before being made a dependency of the stable Government Auditor MVP.

## Why the System Uses a Hybrid Approach

Not every dark pattern requires machine learning.

Some behaviours are directly observable and are better handled through deterministic verification.

```text
Unexpected cart item       → Browser state
Price increase             → Price comparison
Timer reset                → Behavioural replay
Blocked payment action     → Interaction state
Manipulative language      → NLP / ML
```

This allows SENTINEL to use the most appropriate detection method for each pattern rather than applying ML indiscriminately.

## Scope

### Current Government Auditor MVP

The core prototype demonstrates:

- Complete journey auditing
- Five dark-pattern detectors
- Browser-state capture
- Screenshot evidence
- Evidence Graph
- Behavioural replay
- Database persistence
- SHA-256 evidence hashing
- Human Confirm / Reject review
- Controlled clean-vs-manipulative testing

### Planned Extensions

Future development includes:

- Larger multilingual datasets
- Indic-language NLP
- More dark-pattern categories
- Production-scale website auditing
- Distributed browser workers
- Multimodal evidence analysis
- Advanced semantic classification
- Citizen Browser Extension
- Regulator-facing deployment

The **Citizen Browser Extension is intentionally outside the current 36-hour Government Auditor MVP** so that the core auditing and evidence engine remains the primary focus.

## Design Philosophy

SENTINEL follows four principles:

**Detect** — Identify observable or semantic indicators of manipulative behaviour.

**Verify** — Reproduce suspicious behaviour whenever possible.

**Preserve** — Maintain screenshots, state changes, logs, findings and integrity hashes.

**Review** — Present evidence to a human investigator for final assessment.

```text
Detect
  ↓
Verify
  ↓
Preserve Evidence
  ↓
Human Review
```

## Limitations

SENTINEL is a hackathon/research prototype.

The controlled demonstration environment does not represent the complete complexity of the live web.

Detection results should therefore be interpreted as **investigative evidence and signals**, not autonomous legal determinations.

The experimental NLP/ML component also requires larger, representative multilingual datasets and rigorous evaluation before production deployment.

## Future Vision

The long-term goal is to develop SENTINEL into a regulatory auditing platform capable of:

```text
Large-Scale Web Auditing
          ↓
Journey Reconstruction
          ↓
Behavioural + Semantic Detection
          ↓
Cross-Session Verification
          ↓
Evidence Graph
          ↓
Regulatory Investigation
```

The system can eventually support more dark-pattern categories, Indian languages, multimodal evidence, scalable browser workers, and regulator-facing workflows.

## Team

**SENTINEL — SIH Team**

Developed as a Smart India Hackathon prototype focused on automated regulatory auditing and consumer protection.

## License

This project is licensed under the **Apache License 2.0**.

See the `LICENSE` file for the full license text.

## Disclaimer

SENTINEL is a research and hackathon prototype intended to demonstrate automated auditing, behavioural verification, and evidence collection.

It does not provide legal advice and does not make autonomous legal determinations.
