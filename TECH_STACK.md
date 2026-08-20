# Sentinel MVP Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Browser automation | Playwright | Full journey execution, evidence capture and fresh-session replay |
| Detection | Hybrid rules + language analysis | Objective state checks plus manipulative-language analysis |
| Model serving / backend API | FastAPI | Audit orchestration, APIs and evidence access |
| Evidence store | MySQL | Audits, journey steps, findings, replay results and review state |
| Frontend | React + Vite | Government investigation console |
| Evidence files | Local evidence store | Screenshots and replay artefacts |

## Planned ML layer

The proposed multilingual model layer can use **XLM-R Base or IndicBERT v2** for classification of confirm-shaming, trick wording and related language patterns.

The current MVP should not claim that a trained XLM-R/IndicBERT model is already deployed unless the team has trained and integrated it. The current prototype proves the end-to-end evidence pipeline first.

## Architecture

Website
→ Playwright Journey
→ State + Screenshots
→ Hybrid Detection
→ Fresh-Session Replay
→ MySQL Evidence Store
→ Investigation Console
→ Human Review


## Evidence integrity

Every captured screenshot is SHA-256 hashed when it is stored. The investigation console displays a shortened hash while the API retains the complete digest. This makes the prototype's evidence trail demonstrable without claiming a full production chain-of-custody system.


## Current MVP ML status

The end-to-end prototype currently uses a lightweight language heuristic for Confirm Shaming. XLM-R Base / IndicBERT v2 are the proposed multilingual ML models for the next integration step. Do not present a trained model as deployed unless the team has actually trained and integrated it.
