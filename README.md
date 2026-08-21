# SENTINEL — SIH Core MVP Prototype

This is the **Government Auditor** MVP. The Citizen Browser Extension is intentionally not part of the 36-hour core build.

## What the prototype actually does 

1. Starts a controlled demo commerce website with a manipulative mode and a clean control mode.
2. FastAPI creates an audit record and launches Playwright.
3. Playwright performs Search → Product → Cart → Review → Checkout.
4. Every step gets a real screenshot and captured browser state.
5. Detectors inspect observed state:
   * Basket Sneaking
   * Drip Pricing
   * Confirm Shaming (prototype language heuristic)
   * False Urgency
   * Forced Action
6. False Urgency is replayed in a fresh browser session.
7. Findings and replay results are stored in the database.
8. The investigation console shows the journey, evidence graph, replay result and human Confirm/Reject controls.

## Database

MySQL is the intended architecture. If MySQL is not running, the backend automatically uses local SQLite so the team can still demo the system.

## Run

### One-command Docker demo

From the project folder:

    docker compose up --build

Then open:

    http://127.0.0.1:5173

This starts **MySQL + DarkShop + FastAPI/Playwright backend + React investigation console**. The backend waits for MySQL health before starting the audit service.

### Local development

The existing Windows and macOS/Linux scripts can still be used for development. For the intended judge demo, Docker Compose is the most reproducible path.

## Recommended judge demo

1. Click **Run Manipulative Audit**.
2. Watch the five journey screenshots appear.
3. Show the Evidence Graph.
4. Show the False Urgency fresh-session replay.
5. Open each finding and point to the captured evidence.
6. Click **Confirm finding** on one finding.
7. Run **Clean Control** and show that the clean journey produces no dark-pattern findings.

## Scope discipline

The extension, full 13-category coverage, production-scale crawling and advanced multilingual model are future phases. The MVP proves the central evidence engine first.
abcd