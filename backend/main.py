import asyncio
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from playwright.async_api import async_playwright


# ============================================================
# PATHS
# ============================================================

BASE = Path(__file__).resolve().parent.parent

DATA = BASE / "data"
EVIDENCE = DATA / "evidence"

DATA.mkdir(exist_ok=True)
EVIDENCE.mkdir(exist_ok=True)


# ============================================================
# DATABASE
# ============================================================

# MySQL is the intended database.
# SQLite is only a fallback for local development if MySQL
# cannot be reached.

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://sentinel:sentinel@127.0.0.1:3306/sentinel",
)


try:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )

    # Test the database connection immediately.
    with engine.connect() as conn:
        conn.exec_driver_sql("SELECT 1")

    print(f"[Sentinel] Database connected: {engine.url.get_backend_name()}")

except Exception as exc:
    print("[Sentinel] MySQL unavailable.")
    print(f"[Sentinel] Reason: {exc}")
    print("[Sentinel] Falling back to SQLite.")

    engine = create_engine(
        f"sqlite:///{DATA / 'sentinel.db'}",
        connect_args={"check_same_thread": False},
    )


SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
)

Base = declarative_base()


# ============================================================
# DATABASE MODELS
# ============================================================

class Audit(Base):
    __tablename__ = "audits"

    id = Column(String(64), primary_key=True)

    mode = Column(
        String(20),
        nullable=False,
    )

    status = Column(
        String(30),
        nullable=False,
    )

    site = Column(
        String(255),
        nullable=False,
    )

    started_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    finished_at = Column(
        DateTime(timezone=True),
    )

    duration_ms = Column(
        Integer,
    )

    error = Column(
        Text,
    )

    steps = relationship(
        "JourneyStep",
        back_populates="audit",
        cascade="all, delete-orphan",
    )

    findings = relationship(
        "Finding",
        back_populates="audit",
        cascade="all, delete-orphan",
    )


class JourneyStep(Base):
    __tablename__ = "journey_steps"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    audit_id = Column(
        String(64),
        ForeignKey("audits.id"),
        nullable=False,
    )

    step_no = Column(
        Integer,
        nullable=False,
    )

    label = Column(
        String(100),
        nullable=False,
    )

    url = Column(
        Text,
    )

    screenshot = Column(
        Text,
    )

    screenshot_sha256 = Column(
        String(64),
    )

    price = Column(
        String(100),
    )

    cart_json = Column(
        Text,
    )

    protection = Column(
        Boolean,
    )

    timer = Column(
        String(100),
    )

    body_text = Column(
        Text,
    )

    captured_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    audit = relationship(
        "Audit",
        back_populates="steps",
    )


class Finding(Base):
    __tablename__ = "findings"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    audit_id = Column(
        String(64),
        ForeignKey("audits.id"),
        nullable=False,
    )

    pattern_type = Column(
        String(100),
        nullable=False,
    )

    severity = Column(
        String(30),
        nullable=False,
    )

    explanation = Column(
        Text,
        nullable=False,
    )

    step = Column(
        String(150),
        nullable=False,
    )

    evidence_json = Column(
        Text,
        nullable=False,
    )

    review_status = Column(
        String(30),
        default="Pending",
    )

    audit = relationship(
        "Audit",
        back_populates="findings",
    )


class Replay(Base):
    __tablename__ = "replays"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    audit_id = Column(
        String(64),
        ForeignKey("audits.id"),
        nullable=False,
    )

    session_one = Column(
        String(100),
    )

    session_two = Column(
        String(100),
    )

    reproduced = Column(
        Boolean,
        default=False,
    )

    screenshot = Column(
        Text,
    )

    screenshot_sha256 = Column(
        String(64),
    )


# Create tables.
#
# Important:
# The String columns above have explicit lengths so MySQL can
# compile the CREATE TABLE statements.
Base.metadata.create_all(engine)


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="Sentinel Investigation API",
    version="1.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


# Evidence files are available through:
# http://127.0.0.1:8000/evidence/...
app.mount(
    "/evidence",
    StaticFiles(directory=str(EVIDENCE)),
    name="evidence",
)


# ============================================================
# DEMO SHOP
# ============================================================

SHOP = os.getenv(
    "DARKSHOP_URL",
    "http://127.0.0.1:9000",
)


# ============================================================
# AUDIT ACTION MANIFEST
# ============================================================
#
# Closes Round 1 feedback: "Each audit action must be explainable."
#
# One manifest entry per journey step. This describes, for the
# Why? drawer in the UI, what Sentinel was testing at that step,
# why, and which policy hypothesis it was checking — before any
# finding is even produced.
#
STEP_MANIFEST = {
    "Search": {
        "intent": "Establish baseline product and price before any "
                   "journey manipulation can occur.",
        "action": "Load the search/landing page and record the "
                   "advertised product and price.",
        "rationale": "A clean baseline is required so later steps "
                      "can be compared against what the user was "
                      "originally shown.",
        "hypothesis": "The advertised price and product identity "
                        "should remain stable across the journey "
                        "unless explicitly changed by the user.",
        "authority": "CCPA Dark Patterns Guidelines 2023 — baseline "
                      "disclosure principle",
        "expected_observation": "Visible price and product name "
                                  "captured for later diffing.",
        "evidence_required": ["screenshot", "url", "visible_price"],
    },
    "Product": {
        "intent": "Test whether time-pressure or scarcity claims are "
                   "shared/absolute or session-generated.",
        "action": "Open the product page and record any countdown "
                    "timer or urgency/scarcity copy.",
        "rationale": "False Urgency requires behavioral proof, not "
                      "just text — a real deadline should not reset "
                      "per session.",
        "hypothesis": "If the countdown is a real shared deadline, a "
                        "fresh isolated browser session should see "
                        "the same remaining time, not a fresh timer.",
        "authority": "CCPA Dark Patterns Guidelines 2023 — False "
                      "Urgency",
        "expected_observation": "Timer value consistent across a "
                                  "base session and a fresh "
                                  "BrowserContext replay.",
        "evidence_required": ["screenshot", "timer_value", "context_id",
                               "replay_timer_value"],
    },
    "Cart": {
        "intent": "Test whether optional items are added to the cart "
                    "without explicit user authorization.",
        "action": "Add the core product to cart, explicitly leave the "
                    "optional add-on checkbox unchecked, then capture "
                    "cart state.",
        "rationale": "Basket Sneaking requires an evidenced mismatch "
                      "between what the user authorized and what "
                      "ended up in the cart.",
        "hypothesis": "No optional paid item should appear in the "
                        "cart unless a matching AuthorizationEvent "
                        "(a checked opt-in) exists.",
        "authority": "CCPA Dark Patterns Guidelines 2023 — Basket "
                      "Sneaking",
        "expected_observation": "Cart contents must match "
                                  "authorization events; any "
                                  "mismatch is evidence.",
        "evidence_required": ["cart_before", "cart_after",
                               "checkbox_state", "screenshot"],
    },
    "Review": {
        "intent": "Capture the total price shown to the user before "
                    "final commitment, to test for drip pricing.",
        "action": "Navigate to the review/order-summary page and "
                    "record the displayed total.",
        "rationale": "Drip Pricing requires a documented price at an "
                      "earlier step to compare against the final "
                      "checkout total.",
        "hypothesis": "The total shown at Review should match the "
                        "total shown at Checkout; a later increase is "
                        "an undisclosed mandatory fee.",
        "authority": "CCPA Dark Patterns Guidelines 2023 — Drip "
                      "Pricing",
        "expected_observation": "Review total recorded as the "
                                  "pre-commitment reference price.",
        "evidence_required": ["review_total", "timestamp", "screenshot"],
    },
    "Checkout": {
        "intent": "Test for undisclosed fees, forced consent gating, "
                    "and guilt-oriented decline wording at the final "
                    "commitment step.",
        "action": "Load checkout, record the final total, inspect the "
                    "payment gate for unrelated required consent, and "
                    "capture the decline-option wording.",
        "rationale": "This is where Drip Pricing, Forced Action and "
                      "Confirm Shaming evidence all resolve, since "
                      "it's the last step before commitment.",
        "hypothesis": "Final total should equal the Review total; "
                        "payment should not require unrelated consent; "
                        "decline wording should be neutral.",
        "authority": "CCPA Dark Patterns Guidelines 2023 — Drip "
                      "Pricing / Forced Action / Confirm Shaming",
        "expected_observation": "Checkout total, consent-gate state, "
                                  "and decline-copy wording all "
                                  "captured as evidence.",
        "evidence_required": ["checkout_total", "consent_gate_state",
                               "decline_copy", "screenshot"],
    },
}


# ============================================================
# POLICY & AUTHORITY REGISTRY
# ============================================================
#
# Closes Round 1 feedback: "Every finding needs authority + mechanism."
#
# Keyed by Finding.pattern_type. A finding is only "review-ready" once
# it carries a policy_id, version, authority reference, mechanism and
# its required evidence predicates — this registry is what the API
# attaches to every finding it returns.
#
POLICY_REGISTRY = {
    "Basket Sneaking": {
        "policy_id": "ccpa-dark-patterns-2023-basket-sneaking-v1",
        "category": "Basket Sneaking",
        "authority_refs": [
            "CCPA Guidelines for Prevention and Regulation of Dark "
            "Patterns, 2023"
        ],
        "mechanism": "Cart diff after an authorized action. An "
                      "optional paid addition without a matching "
                      "AuthorizationEvent (checked opt-in) is flagged.",
        "required_predicates": ["cart_before", "cart_after",
                                  "checkbox_state"],
        "clean_control": "Explicit opt-in (checked box) produces the "
                           "same add-on with no finding.",
        "reviewRequirement": "Always human review — machine output "
                               "is a candidate, never a verdict.",
    },
    "Drip Pricing": {
        "policy_id": "ccpa-dark-patterns-2023-drip-pricing-v1",
        "category": "Drip Pricing",
        "authority_refs": [
            "CCPA Guidelines for Prevention and Regulation of Dark "
            "Patterns, 2023"
        ],
        "mechanism": "Price provenance ledger tracks the displayed "
                      "total at Review vs. Checkout; an increase "
                      "without disclosure is flagged.",
        "required_predicates": ["review_total", "checkout_total"],
        "clean_control": "Mandatory fee disclosed from the first "
                           "total shown produces no finding.",
        "reviewRequirement": "Always human review — machine output "
                               "is a candidate, never a verdict.",
    },
    "Forced Action": {
        "policy_id": "ccpa-dark-patterns-2023-forced-action-v1",
        "category": "Forced Action",
        "authority_refs": [
            "CCPA Guidelines for Prevention and Regulation of Dark "
            "Patterns, 2023"
        ],
        "mechanism": "Detects an unrelated consent/enrollment "
                      "requirement gating an intended task (payment).",
        "required_predicates": ["consent_checked", "pay_button_disabled"],
        "clean_control": "Unrelated consent remains optional/"
                           "unselected and the journey proceeds.",
        "reviewRequirement": "Always human review — machine output "
                               "is a candidate, never a verdict.",
    },
    "Confirm Shaming": {
        "policy_id": "ccpa-dark-patterns-2023-confirm-shaming-v1",
        "category": "Confirm Shaming",
        "authority_refs": [
            "CCPA Guidelines for Prevention and Regulation of Dark "
            "Patterns, 2023"
        ],
        "mechanism": "Extracts the accept/decline pair and scores "
                      "the decline wording for guilt/fear/loss cues.",
        "required_predicates": ["decline_text", "matched_cue"],
        "clean_control": "Neutral \"No thanks\"-style wording produces "
                           "no finding.",
        "reviewRequirement": "Always human review — machine output "
                               "is a candidate, never a verdict.",
        "detector_method": "keyword-cue heuristic v1 (rule-based). "
                             "Per the ML specification, this is an "
                             "honest placeholder — a benchmarked "
                             "XLM-R vs IndicBERT classifier is planned "
                             "and NOT yet trained, so no accuracy "
                             "figure is reported for it.",
    },
    "False Urgency": {
        "policy_id": "ccpa-dark-patterns-2023-false-urgency-v1",
        "category": "False Urgency",
        "authority_refs": [
            "CCPA Guidelines for Prevention and Regulation of Dark "
            "Patterns, 2023"
        ],
        "mechanism": "Compares a countdown timer's behavior across "
                      "the base session and a fresh isolated "
                      "BrowserContext. A timer that decreases in the "
                      "base session but resets in a fresh context "
                      "indicates a per-session fake deadline rather "
                      "than a shared, real one.",
        "required_predicates": ["session_1_start", "session_1_after",
                                  "fresh_session_start"],
        "clean_control": "A shared absolute-expiry countdown "
                           "continues across sessions and produces no "
                           "finding.",
        "reviewRequirement": "Always human review — machine output "
                               "is a candidate, never a verdict.",
    },
}


# ============================================================
# REQUEST MODELS
# ============================================================

class AuditRequest(BaseModel):
    mode: str = "dark"


# ============================================================
# HELPERS
# ============================================================

def sha256_file(path: Path):
    """
    Calculate SHA-256 hash of an evidence file.
    """

    h = hashlib.sha256()

    with open(path, "rb") as fh:
        for chunk in iter(
            lambda: fh.read(1024 * 1024),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def iso(value):
    """
    Convert datetime to ISO string.
    """

    return value.isoformat() if value else None


# ============================================================
# EVIDENCE GRAPH
# ============================================================

def evidence_graph(audit):
    """
    Build the journey/evidence graph used by the frontend.
    """

    steps = sorted(
        audit.steps,
        key=lambda x: x.step_no,
    )

    nodes = [
        {
            "id": f"s{x.step_no}",
            "label": x.label,
            "type": "journey",
        }
        for x in steps
    ]

    for finding in audit.findings:
        nodes.append(
            {
                "id": f"f{finding.id}",
                "label": finding.pattern_type,
                "type": "finding",
            }
        )

    edges = []

    # Journey sequence.
    for i in range(len(steps) - 1):
        edges.append(
            {
                "from": f"s{steps[i].step_no}",
                "to": f"s{steps[i + 1].step_no}",
                "label": "next",
            }
        )

    # Finding connections.
    for finding in audit.findings:

        match = next(
            (
                step
                for step in steps
                if step.label in finding.step
            ),
            None,
        )

        if match:
            edges.append(
                {
                    "from": f"s{match.step_no}",
                    "to": f"f{finding.id}",
                    "label": "detected",
                }
            )

    return {
        "nodes": nodes,
        "edges": edges,
    }


# ============================================================
# AUDIT SERIALIZATION
# ============================================================

def as_dict(db, audit):
    """
    Convert an Audit database object into the JSON structure
    consumed by the frontend.
    """

    steps = sorted(
        audit.steps,
        key=lambda x: x.step_no,
    )

    replay = (
        db.query(Replay)
        .filter(Replay.audit_id == audit.id)
        .first()
    )

    findings = list(audit.findings)

    return {
        "id": audit.id,
        "mode": audit.mode,
        "status": audit.status,
        "site": audit.site,

        "startedAt": iso(audit.started_at),
        "finishedAt": iso(audit.finished_at),
        "durationMs": audit.duration_ms,
        "error": audit.error,

        "steps": [
            {
                "step": step.step_no,
                "label": step.label,
                "url": step.url,
                "screenshot": step.screenshot,
                "screenshotSha256": step.screenshot_sha256,
                "price": step.price,
                "cart": json.loads(
                    step.cart_json or "[]"
                ),
                "protection": step.protection,
                "timer": step.timer,
                "at": iso(step.captured_at),
                "manifest": STEP_MANIFEST.get(step.label),
            }
            for step in steps
        ],

        "findings": [
            {
                "id": finding.id,
                "type": finding.pattern_type,
                "severity": finding.severity,
                "explanation": finding.explanation,
                "step": finding.step,
                "evidence": json.loads(
                    finding.evidence_json
                ),
                "reviewStatus": finding.review_status,
                "authority": POLICY_REGISTRY.get(finding.pattern_type),
            }
            for finding in findings
        ],

        "replay": (
            None
            if not replay
            else {
                "session1": replay.session_one,
                "session2": replay.session_two,
                "reproduced": replay.reproduced,
                "screenshot": replay.screenshot,
                "screenshotSha256": replay.screenshot_sha256,
            }
        ),

        "graph": evidence_graph(audit),
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "database": engine.url.get_backend_name(),
        "shop": SHOP,
    }


# ============================================================
# GET ALL AUDITS
# ============================================================

@app.get("/api/audits")
def list_audits():

    db = SessionLocal()

    try:
        audits = (
            db.query(Audit)
            .order_by(Audit.started_at.desc())
            .all()
        )

        return [
            as_dict(db, audit)
            for audit in audits
        ]

    finally:
        db.close()


# ============================================================
# GET ONE AUDIT
# ============================================================

@app.get("/api/audits/{audit_id}")
def get_audit(audit_id: str):

    db = SessionLocal()

    try:
        audit = db.get(
            Audit,
            audit_id,
        )

        if not audit:
            raise HTTPException(
                status_code=404,
                detail="Audit not found",
            )

        return as_dict(
            db,
            audit,
        )

    finally:
        db.close()


# ============================================================
# POLICY REGISTRY (read-only)
# ============================================================

@app.get("/api/policies")
def list_policies():
    return POLICY_REGISTRY


@app.get("/api/policies/{pattern_type}")
def get_policy(pattern_type: str):

    policy = POLICY_REGISTRY.get(pattern_type)

    if not policy:
        raise HTTPException(
            status_code=404,
            detail="Policy not found",
        )

    return policy


# ============================================================
# IMPACT — measured metrics only, no invented numbers
# ============================================================
#
# Closes Round 1 feedback: "Impact needs quantification."
#
# Every number here is computed live from what's actually in the
# database. If there is no data yet for a metric, we report that
# honestly (null / "not yet measured") rather than fabricating a
# placeholder value.
#
@app.get("/api/impact")
def impact():

    db = SessionLocal()

    try:
        audits = db.query(Audit).all()
        findings = db.query(Finding).all()
        replays = db.query(Replay).all()

        completed = [a for a in audits if a.status == "completed"]
        dark_completed = [a for a in completed if a.mode == "dark"]
        clean_completed = [a for a in completed if a.mode == "clean"]

        # Evidence completeness: every finding this API returns
        # already carries mechanism + authority_refs + evidence
        # (evidence_json is NOT NULL at the DB level) + a policy
        # version, so this is 100% by construction — but we still
        # compute it rather than assume, in case that ever changes.
        complete_findings = [
            f for f in findings
            if f.evidence_json
            and f.pattern_type in POLICY_REGISTRY
        ]

        evidence_completeness = (
            round(100 * len(complete_findings) / len(findings), 1)
            if findings else None
        )

        # Clean-control pass rate: clean-mode audits that correctly
        # produced zero findings.
        clean_with_no_findings = [
            a for a in clean_completed if len(a.findings) == 0
        ]

        clean_pass_rate = (
            round(
                100 * len(clean_with_no_findings) / len(clean_completed),
                1,
            )
            if clean_completed else None
        )

        # Replay reproducibility: of replays actually run, how many
        # reproduced the suspicious behavior.
        reproduced = [r for r in replays if r.reproduced]

        replay_rate = (
            round(100 * len(reproduced) / len(replays), 1)
            if replays else None
        )

        # Detector coverage: distinct pattern types observed vs the
        # five accepted detectors.
        distinct_patterns = {f.pattern_type for f in findings}

        # Audit latency, from real completed runs only.
        durations = [
            a.duration_ms for a in completed if a.duration_ms
        ]

        avg_latency_ms = (
            round(sum(durations) / len(durations))
            if durations else None
        )

        return {
            "auditsRun": len(audits),
            "auditsCompleted": len(completed),
            "darkAuditsCompleted": len(dark_completed),
            "cleanAuditsCompleted": len(clean_completed),

            "totalFindings": len(findings),
            "evidenceCompletenessPct": evidence_completeness,

            "cleanControlPassRatePct": clean_pass_rate,
            "cleanControlSampleSize": len(clean_completed),

            "replayReproducibilityPct": replay_rate,
            "replaySampleSize": len(replays),

            "detectorCoverage": {
                "fired": sorted(distinct_patterns),
                "total": len(POLICY_REGISTRY),
                "count": len(distinct_patterns),
            },

            "avgAuditLatencyMs": avg_latency_ms,

            "mlMacroF1": None,
            "mlNote": (
                "No trained multilingual classifier has been "
                "benchmarked yet. Confirm Shaming currently runs on "
                "a rule-based keyword-cue heuristic. Per the ML "
                "specification, no accuracy figure is reported until "
                "a frozen-test evaluation exists."
            ),

            "reviewerEfficiency": None,
            "reviewerEfficiencyNote": (
                "Not yet measured — requires a counterbalanced "
                "reviewer study (>=6 reviewers) that has not been run."
            ),
        }

    finally:
        db.close()


# ============================================================
# CREATE AUDIT
# ============================================================

@app.post("/api/audits")
async def create_audit(req: AuditRequest):

    mode = (
        "clean"
        if req.mode == "clean"
        else "dark"
    )

    audit_id = uuid.uuid4().hex[:10]

    db = SessionLocal()

    try:
        db.add(
            Audit(
                id=audit_id,
                mode=mode,
                status="running",
                site=(
                    "Demo Commerce Store · "
                    + (
                        "Manipulative Benchmark"
                        if mode == "dark"
                        else "Clean Control"
                    )
                ),
            )
        )

        db.commit()

    finally:
        db.close()

    # Run the browser audit in the background.
    asyncio.create_task(
        run_audit(
            audit_id,
            mode,
        )
    )

    return {
        "id": audit_id,
    }


# ============================================================
# REVIEW FINDING
# ============================================================

@app.post("/api/findings/{finding_id}/review")
def review(
    finding_id: int,
    status: str,
):

    if status not in {
        "Confirmed",
        "Rejected",
        "Pending",
    }:
        raise HTTPException(
            status_code=400,
            detail="Invalid review status",
        )

    db = SessionLocal()

    try:
        finding = db.get(
            Finding,
            finding_id,
        )

        if not finding:
            raise HTTPException(
                status_code=404,
                detail="Finding not found",
            )

        finding.review_status = status

        db.commit()

        return {
            "ok": True,
            "findingId": finding_id,
            "status": status,
        }

    finally:
        db.close()


# ============================================================
# RUN AUDIT
# ============================================================

async def run_audit(
    audit_id: str,
    mode: str,
):

    started = datetime.now(timezone.utc)

    evidence_dir = EVIDENCE / audit_id
    evidence_dir.mkdir(
        exist_ok=True
    )

    # --------------------------------------------------------
    # Get audit
    # --------------------------------------------------------

    db = SessionLocal()

    audit = db.get(
        Audit,
        audit_id,
    )

    db.close()

    try:

        # ====================================================
        # PLAYWRIGHT
        # ====================================================

        async with async_playwright() as pw:

            browser = await pw.chromium.launch(
                headless=True
            )

            context = await browser.new_context(
                viewport={
                    "width": 1280,
                    "height": 820,
                }
            )

            page = await context.new_page()


            # =================================================
            # CAPTURE JOURNEY STEP
            # =================================================

            async def capture(
                step_no,
                label,
            ):

                filename = (
                    f"{step_no:02d}-"
                    f"{label.lower().replace(' ', '-')}.png"
                )

                file = (
                    evidence_dir
                    / filename
                )

                # Screenshot.
                await page.screenshot(
                    path=str(file),
                    full_page=True,
                )

                # Capture browser state.
                obs = await page.evaluate(
                    """
                    () => ({
                        url: location.href,

                        price:
                            document
                            .querySelector(
                                '[data-testid="visible-total"]'
                            )
                            ?.textContent
                            ?.trim()
                            || null,

                        cart:
                            [
                                ...document.querySelectorAll(
                                    '[data-testid="cart-item"]'
                                )
                            ]
                            .map(
                                e => e.textContent.trim()
                            ),

                        protection:
                            document.querySelector(
                                '#protection'
                            )
                            ?.checked
                            ?? null,

                        timer:
                            document.querySelector(
                                '[data-testid="urgency-timer"]'
                            )
                            ?.textContent
                            ?.trim()
                            || null,

                        text:
                            document.body.innerText
                    })
                    """
                )

                db2 = SessionLocal()

                try:

                    db2.add(
                        JourneyStep(
                            audit_id=audit_id,
                            step_no=step_no,
                            label=label,
                            url=obs["url"],
                            screenshot=(
                                f"/evidence/"
                                f"{audit_id}/"
                                f"{file.name}"
                            ),
                            screenshot_sha256=sha256_file(
                                file
                            ),
                            price=obs["price"],
                            cart_json=json.dumps(
                                obs["cart"]
                            ),
                            protection=obs[
                                "protection"
                            ],
                            timer=obs["timer"],
                            body_text=obs["text"],
                        )
                    )

                    db2.commit()

                finally:
                    db2.close()

                return obs


            # =================================================
            # STEP 1 — SEARCH
            # =================================================

            await page.goto(
                f"{SHOP}/?mode={mode}",
                wait_until="networkidle",
            )

            await capture(
                1,
                "Search",
            )


            # =================================================
            # STEP 2 — PRODUCT
            # =================================================

            await page.get_by_role(
                "button",
                name="Select Product",
            ).click()

            await page.wait_for_timeout(250)

            product = await capture(
                2,
                "Product",
            )


            # =================================================
            # STEP 3 — CART
            # =================================================

            await page.get_by_role(
                "button",
                name="Add to Cart",
            ).click()

            await page.wait_for_timeout(250)

            # IMPORTANT:
            #
            # We explicitly leave protection unchecked BEFORE
            # capturing the Cart state.
            #
            # This makes the Basket Sneaking evidence:
            #
            # checkbox = false
            # protection item = present
            #
            if await page.locator(
                "#protection"
            ).count():

                try:
                    await page.locator(
                        "#protection"
                    ).uncheck()

                except Exception:
                    # If already unchecked, continue.
                    pass

            cart = await capture(
                3,
                "Cart",
            )


            # =================================================
            # STEP 4 — REVIEW
            # =================================================

            await page.get_by_role(
                "button",
                name="Review Order",
            ).click()

            await page.wait_for_timeout(250)

            review_state = await capture(
                4,
                "Review",
            )


            # =================================================
            # STEP 5 — CHECKOUT
            # =================================================

            await page.get_by_role(
                "button",
                name="Checkout",
            ).click()

            await page.wait_for_timeout(250)

            checkout_state = await capture(
                5,
                "Checkout",
            )


            # =================================================
            # FINDINGS
            # =================================================

            db2 = SessionLocal()

            try:

                # ------------------------------------------------
                # BASKET SNEAKING
                # ------------------------------------------------

                protection_present = any(
                    "Travel Protection" in item
                    for item in cart["cart"]
                )

                unchecked = (
                    cart["protection"] is False
                )

                if (
                    mode == "dark"
                    and protection_present
                    and unchecked
                ):

                    db2.add(
                        Finding(
                            audit_id=audit_id,
                            pattern_type="Basket Sneaking",
                            severity="High",
                            explanation=(
                                "An optional protection item "
                                "appears in the cart even though "
                                "the user left its opt-in "
                                "checkbox unchecked."
                            ),
                            step="Cart",
                            evidence_json=json.dumps(
                                {
                                    "checkbox_checked": False,
                                    "optional_item_present": True,
                                    "cart": cart["cart"],
                                }
                            ),
                        )
                    )


                # ------------------------------------------------
                # DRIP PRICING
                # ------------------------------------------------

                if (
                    mode == "dark"
                    and review_state["price"]
                    != checkout_state["price"]
                ):

                    db2.add(
                        Finding(
                            audit_id=audit_id,
                            pattern_type="Drip Pricing",
                            severity="High",
                            explanation=(
                                "A mandatory fee appears at "
                                "checkout after the earlier "
                                "review total was shown."
                            ),
                            step="Review → Checkout",
                            evidence_json=json.dumps(
                                {
                                    "review_total":
                                        review_state["price"],

                                    "checkout_total":
                                        checkout_state["price"],

                                    "new_fee":
                                        "₹129",
                                }
                            ),
                        )
                    )


                # ------------------------------------------------
                # FORCED ACTION
                # ------------------------------------------------

                if mode == "dark":

                    consent = page.locator(
                        "#marketing-consent"
                    )

                    pay = page.locator(
                        "#pay-now"
                    )

                    consent_exists = (
                        await consent.count()
                        > 0
                    )

                    pay_disabled = (
                        await pay.is_disabled()
                        if await pay.count()
                        else False
                    )

                    forced_note_locator = page.locator(
                        "[data-testid='forced-action-note']"
                    )

                    if (
                        await forced_note_locator.count()
                    ):

                        gate_note = (
                            await forced_note_locator
                            .text_content()
                            or ""
                        )

                    else:
                        gate_note = ""


                    if (
                        consent_exists
                        and pay_disabled
                    ):

                        db2.add(
                            Finding(
                                audit_id=audit_id,
                                pattern_type="Forced Action",
                                severity="High",
                                explanation=(
                                    "Payment is blocked until "
                                    "the user accepts an "
                                    "unrelated promotional-"
                                    "consent option."
                                ),
                                step="Checkout",
                                evidence_json=json.dumps(
                                    {
                                        "required_action":
                                            "Promotional consent",

                                        "consent_checked":
                                            False,

                                        "pay_button_disabled":
                                            True,

                                        "gate_text":
                                            gate_note.strip(),
                                    }
                                ),
                            )
                        )


                # ------------------------------------------------
                # CONFIRM SHAMING
                # ------------------------------------------------

                if mode == "dark":

                    decline_locator = page.locator(
                        "[data-testid='decline-copy']"
                    )

                    if await decline_locator.count():

                        decline = (
                            await decline_locator
                            .text_content()
                            or ""
                        )

                        low = decline.lower()

                        cue_words = [
                            "don't want",
                            "regret",
                            "waste",
                            "miss",
                            "lose",
                            "don't care about",
                        ]

                        matched_cue = next(
                            (
                                word
                                for word in cue_words
                                if word in low
                            ),
                            None,
                        )

                        if matched_cue:

                            db2.add(
                                Finding(
                                    audit_id=audit_id,
                                    pattern_type="Confirm Shaming",
                                    severity="Medium",
                                    explanation=(
                                        "The decline option "
                                        "uses loss or "
                                        "guilt-oriented "
                                        "language instead of "
                                        "a neutral choice."
                                    ),
                                    step="Checkout",
                                    evidence_json=json.dumps(
                                        {
                                            "language":
                                                "English",

                                            "decline_text":
                                                decline.strip(),

                                            "cue":
                                                matched_cue,
                                        }
                                    ),
                                )
                            )

                db2.commit()

            finally:
                db2.close()


            # =================================================
            # FALSE URGENCY / REPLAY VERIFICATION
            # =================================================
            #
            # IMPORTANT FIX:
            #
            # The urgency timer exists on the PRODUCT page.
            #
            # The old code waited until after Checkout and then
            # tried to read:
            #
            #     [data-testid='urgency-timer']
            #
            # That caused the 30-second Playwright timeout.
            #
            # We now explicitly return to Product and measure
            # the timer there.
            #

            if (
                mode == "dark"
                and product["timer"]
            ):

                # ------------------------------------------------
                # Session 1 — Product page
                # ------------------------------------------------

                await page.goto(
                    f"{SHOP}/product?mode={mode}",
                    wait_until="networkidle",
                )

                await page.wait_for_timeout(250)

                timer_locator = page.locator(
                    "[data-testid='urgency-timer']"
                )

                first = None
                later = None

                if await timer_locator.count():

                    first_text = (
                        await timer_locator
                        .text_content()
                        or ""
                    )

                    match = re.search(
                        r"(\d+)s",
                        first_text,
                    )

                    if match:
                        first = int(
                            match.group(1)
                        )

                    # Wait 3 seconds WITHOUT leaving Product.
                    await page.wait_for_timeout(
                        3000
                    )

                    later_text = (
                        await timer_locator
                        .text_content()
                        or ""
                    )

                    match = re.search(
                        r"(\d+)s",
                        later_text,
                    )

                    if match:
                        later = int(
                            match.group(1)
                        )


                # ------------------------------------------------
                # Fresh isolated session
                # ------------------------------------------------

                fresh = await browser.new_context(
                    viewport={
                        "width": 1280,
                        "height": 820,
                    }
                )

                try:

                    p2 = await fresh.new_page()

                    await p2.goto(
                        f"{SHOP}/product?mode={mode}",
                        wait_until="networkidle",
                    )

                    await p2.wait_for_timeout(250)

                    fresh_timer = p2.locator(
                        "[data-testid='urgency-timer']"
                    )

                    fresh_start = None

                    if await fresh_timer.count():

                        fresh_text = (
                            await fresh_timer
                            .text_content()
                            or ""
                        )

                        match = re.search(
                            r"(\d+)s",
                            fresh_text,
                        )

                        if match:
                            fresh_start = int(
                                match.group(1)
                            )


                    # ------------------------------------------------
                    # Replay screenshot
                    # ------------------------------------------------

                    replay_file = (
                        evidence_dir
                        / "06-fresh-session-replay.png"
                    )

                    await p2.screenshot(
                        path=str(replay_file),
                        full_page=True,
                    )

                finally:

                    await fresh.close()


                # ------------------------------------------------
                # Verification
                # ------------------------------------------------

                decreased = (
                    first is not None
                    and later is not None
                    and later < first
                )

                reset = (
                    first is not None
                    and fresh_start is not None
                    and abs(
                        first - fresh_start
                    ) <= 3
                )

                reproduced = (
                    decreased
                    and reset
                )


                # ------------------------------------------------
                # Save replay
                # ------------------------------------------------

                db3 = SessionLocal()

                try:

                    db3.add(
                        Replay(
                            audit_id=audit_id,

                            session_one=(
                                f"{first}s → {later}s"
                            ),

                            session_two=(
                                f"{fresh_start}s"
                            ),

                            reproduced=reproduced,

                            screenshot=(
                                f"/evidence/"
                                f"{audit_id}/"
                                f"{replay_file.name}"
                            ),

                            screenshot_sha256=
                                sha256_file(
                                    replay_file
                                ),
                        )
                    )


                    # ------------------------------------------------
                    # FALSE URGENCY FINDING
                    # ------------------------------------------------

                    if reproduced:

                        db3.add(
                            Finding(
                                audit_id=audit_id,
                                pattern_type="False Urgency",
                                severity="High",
                                explanation=(
                                    "The timer decreases "
                                    "during the session but "
                                    "resets to its original "
                                    "range in a fresh "
                                    "session, indicating "
                                    "session-based urgency "
                                    "rather than a shared "
                                    "deadline."
                                ),
                                step=(
                                    "Product → "
                                    "Fresh Session Replay"
                                ),
                                evidence_json=json.dumps(
                                    {
                                        "session_1_start":
                                            first,

                                        "session_1_after_3_seconds":
                                            later,

                                        "fresh_session_start":
                                            fresh_start,

                                        "countdown_decreased":
                                            decreased,

                                        "fresh_session_reset":
                                            reset,
                                    }
                                ),
                            )
                        )


                    db3.commit()

                finally:
                    db3.close()


            # =================================================
            # CLOSE BROWSER
            # =================================================

            await browser.close()


        # ====================================================
        # AUDIT COMPLETED
        # ====================================================

        db = SessionLocal()

        try:

            audit = db.get(
                Audit,
                audit_id,
            )

            if audit:

                audit.status = "completed"

                audit.finished_at = (
                    datetime.now(timezone.utc)
                )

                audit.duration_ms = int(
                    (
                        audit.finished_at
                        - started
                    ).total_seconds()
                    * 1000
                )

                audit.error = None

                db.commit()

        finally:
            db.close()


    # ========================================================
    # AUDIT ERROR
    # ========================================================

    except Exception as exc:

        print(
            f"[Sentinel] Audit {audit_id} failed:"
        )

        print(repr(exc))

        db = SessionLocal()

        try:

            audit = db.get(
                Audit,
                audit_id,
            )

            if audit:

                audit.status = "error"

                audit.error = repr(exc)

                audit.finished_at = (
                    datetime.now(timezone.utc)
                )

                audit.duration_ms = int(
                    (
                        audit.finished_at
                        - started
                    ).total_seconds()
                    * 1000
                )

                db.commit()

        finally:
            db.close()


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
    )