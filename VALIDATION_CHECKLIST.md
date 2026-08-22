# Pre-Demo Validation

Run:

    docker compose up --build

If Docker Desktop is not installed, use the local-development scripts instead.

Then verify:

1. `http://127.0.0.1:5173` opens.
2. The console says **PostgreSQL** as the evidence store.
3. Click **Run Manipulative Audit**.
4. Five journey steps complete.
5. Findings include the five MVP detectors.
6. False Urgency shows same-session decrease + fresh-session reset.
7. Screenshot SHA-256 values appear.
8. Click Confirm on a finding.
9. Run **Clean Control** and verify the clean journey has no dark-pattern findings.
10. `docker compose down` stops the demo cleanly.

Do not claim XLM-R/IndicBERT is deployed unless the trained model is actually integrated.
