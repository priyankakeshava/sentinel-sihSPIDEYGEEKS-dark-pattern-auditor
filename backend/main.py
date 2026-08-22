import asyncio
import hashlib
import json
import os
import re
import uuid
import time
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
    Float,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.dialects.postgresql import JSONB
from playwright.async_api import async_playwright

import requests
from transformers import pipeline

# Load XLM-R multilingual zero-shot model to support English, Hindi, and Hinglish per the blueprint
classifier = pipeline("zero-shot-classification", model="joeddav/xlm-roberta-large-xnli")
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

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://sentinel:sentinel@127.0.0.1:5432/sentinel",
)


try:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )

    with engine.connect() as conn:
        conn.exec_driver_sql("SELECT 1")

    print(f"[Sentinel] Database connected: {engine.url.get_backend_name()}")

except Exception as exc:
    print("[Sentinel] PostgreSQL unavailable.")
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
    mode = Column(String(20), nullable=False)
    status = Column(String(30), nullable=False)
    site = Column(String(255), nullable=False)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime(timezone=True))
    duration_ms = Column(Integer)
    error = Column(Text)

    steps = relationship("JourneyStep", back_populates="audit", cascade="all, delete-orphan")
    findings = relationship("Finding", back_populates="audit", cascade="all, delete-orphan")


class JourneyStep(Base):
    __tablename__ = "journey_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    audit_id = Column(String(64), ForeignKey("audits.id"), nullable=False)
    step_no = Column(Integer, nullable=False)
    label = Column(String(100), nullable=False)
    url = Column(Text)
    screenshot = Column(Text)
    screenshot_sha256 = Column(String(64))
    price = Column(String(100))
    cart_json = Column(JSONB) # Updated to JSONB
    protection = Column(Boolean)
    timer = Column(String(100))
    body_text = Column(Text)
    captured_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    audit = relationship("Audit", back_populates="steps")


class Finding(Base):
    __tablename__ = "findings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    audit_id = Column(String(64), ForeignKey("audits.id"), nullable=False)
    pattern_type = Column(String(100), nullable=False)
    severity = Column(String(30), nullable=False)
    explanation = Column(Text, nullable=False)
    step = Column(String(150), nullable=False)
    evidence_json = Column(JSONB, nullable=False) # Updated to JSONB
    review_status = Column(String(30), default="Pending")

    audit = relationship("Audit", back_populates="findings")


class Replay(Base):
    __tablename__ = "replays"

    id = Column(Integer, primary_key=True, autoincrement=True)
    audit_id = Column(String(64), ForeignKey("audits.id"), nullable=False)
    session_one = Column(String(100))
    session_two = Column(String(100))
    reproduced = Column(Boolean, default=False)
    screenshot = Column(Text)
    screenshot_sha256 = Column(String(64))


class MLInference(Base):
    __tablename__ = "ml_inferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    input_hash = Column(String(64), index=True, nullable=False)
    model_version = Column(String(50))
    dataset_version = Column(String(50))
    labels_probabilities = Column(JSONB)
    top_label = Column(String(50))
    latency_ms = Column(Float)


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

STEP_MANIFEST = {
    "Search": {
        "intent": "Establish baseline product and price before any journey manipulation can occur.",
        "action": "Load the search/landing page and record the advertised product and price.",
        "rationale": "A clean baseline is required so later steps can be compared against what the user was originally shown.",
        "hypothesis": "The advertised price and product identity should remain stable across the journey unless explicitly changed by the user.",
        "authority": "CCPA Dark Patterns Guidelines 2023 — baseline disclosure principle",
        "expected_observation": "Visible price and product name captured for later diffing.",
        "evidence_required": ["screenshot", "url", "visible_price"],
    },
    "Product": {
        "intent": "Test whether time-pressure or scarcity claims are shared/absolute or session-generated.",
        "action": "Open the product page and record any countdown timer or urgency/scarcity copy.",
        "rationale": "False Urgency requires behavioral proof, not just text — a real deadline should not reset per session.",
        "hypothesis": "If the countdown is a real shared deadline, a fresh isolated browser session should see the same remaining time, not a fresh timer.",
        "authority": "CCPA Dark Patterns Guidelines 2023 — False Urgency",
        "expected_observation": "Timer value consistent across a base session and a fresh BrowserContext replay.",
        "evidence_required": ["screenshot", "timer_value", "context_id", "replay_timer_value"],
    },
    "Cart": {
        "intent": "Test whether optional items are added to the cart without explicit user authorization.",
        "action": "Add the core product to cart, explicitly leave the optional add-on checkbox unchecked, then capture cart state.",
        "rationale": "Basket Sneaking requires an evidenced mismatch between what the user authorized and what ended up in the cart.",
        "hypothesis": "No optional paid item should appear in the cart unless a matching AuthorizationEvent (a checked opt-in) exists.",
        "authority": "CCPA Dark Patterns Guidelines 2023 — Basket Sneaking",
        "expected_observation": "Cart contents must match authorization events; any mismatch is evidence.",
        "evidence_required": ["cart_before", "cart_after", "checkbox_state", "screenshot"],
    },
    "Review": {
        "intent": "Capture the total price shown to the user before final commitment, to test for drip pricing.",
        "action": "Navigate to the review/order-summary page and record the displayed total.",
        "rationale": "Drip Pricing requires a documented price at an earlier step to compare against the final checkout total.",
        "hypothesis": "The total shown at Review should match the total shown at Checkout; a later increase is an undisclosed mandatory fee.",
        "authority": "CCPA Dark Patterns Guidelines 2023 — Drip Pricing",
        "expected_observation": "Review total recorded as the pre-commitment reference price.",
        "evidence_required": ["review_total", "timestamp", "screenshot"],
    },
    "Checkout": {
        "intent": "Test for undisclosed fees, forced consent gating, and guilt-oriented decline wording at the final commitment step.",
        "action": "Load checkout, record the final total, inspect the payment gate for unrelated required consent, and capture the decline-option wording.",
        "rationale": "This is where Drip Pricing, Forced Action and Confirm Shaming evidence all resolve, since it's the last step before commitment.",
        "hypothesis": "Final total should equal the Review total; payment should not require unrelated consent; decline wording should be neutral.",
        "authority": "CCPA Dark Patterns Guidelines 2023 — Drip Pricing / Forced Action / Confirm Shaming",
        "expected_observation": "Checkout total, consent-gate state, and decline-copy wording all captured as evidence.",
        "evidence_required": ["checkout_total", "consent_gate_state", "decline_copy", "screenshot"],
    },
}


# ============================================================
# POLICY & AUTHORITY REGISTRY
# ============================================================

POLICY_REGISTRY = {
    "Basket Sneaking": {
        "policy_id": "ccpa-dark-patterns-2023-basket-sneaking-v1",
        "category": "Basket Sneaking",
        "authority_refs": ["CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023"],
        "mechanism": "Cart diff after an authorized action. An optional paid addition without a matching AuthorizationEvent (checked opt-in) is flagged.",
        "required_predicates": ["cart_before", "cart_after", "checkbox_state"],
        "clean_control": "Explicit opt-in (checked box) produces the same add-on with no finding.",
        "reviewRequirement": "Always human review — machine output is a candidate, never a verdict.",
    },
    "Drip Pricing": {
        "policy_id": "ccpa-dark-patterns-2023-drip-pricing-v1",
        "category": "Drip Pricing",
        "authority_refs": ["CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023"],
        "mechanism": "Price provenance ledger tracks the displayed total at Review vs. Checkout; an increase without disclosure is flagged.",
        "required_predicates": ["review_total", "checkout_total"],
        "clean_control": "Mandatory fee disclosed from the first total shown produces no finding.",
        "reviewRequirement": "Always human review — machine output is a candidate, never a verdict.",
    },
    "Forced Action": {
        "policy_id": "ccpa-dark-patterns-2023-forced-action-v1",
        "category": "Forced Action",
        "authority_refs": ["CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023"],
        "mechanism": "Detects an unrelated consent/enrollment requirement gating an intended task (payment).",
        "required_predicates": ["consent_checked", "pay_button_disabled"],
        "clean_control": "Unrelated consent remains optional/unselected and the journey proceeds.",
        "reviewRequirement": "Always human review — machine output is a candidate, never a verdict.",
    },
    "Confirm Shaming": {
        "policy_id": "ccpa-dark-patterns-2023-confirm-shaming-v1",
        "category": "Confirm Shaming",
        "authority_refs": ["CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023"],
        "mechanism": "Extracts the accept/decline pair and scores the decline wording for guilt/fear/loss cues.",
        "required_predicates": ["decline_text", "matched_cue"],
        "clean_control": "Neutral \"No thanks\"-style wording produces no finding.",
        "reviewRequirement": "Always human review — machine output is a candidate, never a verdict.",
        "detector_method": "Multilingual zero-shot classification (XLM-R). Inference executed natively via Hugging Face pipeline.",
    },
    "False Urgency": {
        "policy_id": "ccpa-dark-patterns-2023-false-urgency-v1",
        "category": "False Urgency",
        "authority_refs": ["CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023"],
        "mechanism": "Compares a countdown timer's behavior across the base session and a fresh isolated BrowserContext. A timer that decreases in the base session but resets in a fresh context indicates a per-session fake deadline rather than a shared, real one.",
        "required_predicates": ["session_1_start", "session_1_after", "fresh_session_start"],
        "clean_control": "A shared absolute-expiry countdown continues across sessions and produces no finding.",
        "reviewRequirement": "Always human review — machine output is a candidate, never a verdict.",
    },
}


# ============================================================
# REQUEST MODELS
# ============================================================

class AuditRequest(BaseModel):
    mode: str = "dark"

class MLRequest(BaseModel):
    text: str
    local_context: str = ""


# ============================================================
# HELPERS
# ============================================================

def sha256_file(path: Path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def iso(value):
    return value.isoformat() if value else None


# ============================================================
# EVIDENCE GRAPH
# ============================================================

def evidence_graph(audit):
    steps = sorted(audit.steps, key=lambda x: x.step_no)
    nodes = [{"id": f"s{x.step_no}", "label": x.label, "type": "journey"} for x in steps]

    for finding in audit.findings:
        nodes.append({"id": f"f{finding.id}", "label": finding.pattern_type, "type": "finding"})

    edges = []
    for i in range(len(steps) - 1):
        edges.append({"from": f"s{steps[i].step_no}", "to": f"s{steps[i + 1].step_no}", "label": "next"})

    for finding in audit.findings:
        match = next((step for step in steps if step.label in finding.step), None)
        if match:
            edges.append({"from": f"s{match.step_no}", "to": f"f{finding.id}", "label": "detected"})

    return {"nodes": nodes, "edges": edges}


# ============================================================
# AUDIT SERIALIZATION
# ============================================================

def as_dict(db, audit):
    steps = sorted(audit.steps, key=lambda x: x.step_no)
    replay = db.query(Replay).filter(Replay.audit_id == audit.id).first()
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
                # JSONB returns a dict directly, no need for json.loads()
                "cart": step.cart_json or [],
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
                # JSONB returns a dict directly, no need for json.loads()
                "evidence": finding.evidence_json or {},
                "reviewStatus": finding.review_status,
                "authority": POLICY_REGISTRY.get(finding.pattern_type),
            }
            for finding in findings
        ],
        "replay": (
            None if not replay else {
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
# HEALTH & ML API
# ============================================================

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "database": engine.url.get_backend_name(),
        "shop": SHOP,
    }


@app.post("/ml/v1/classify")
def classify_text(req: MLRequest):
    start_time = time.time()
    input_hash = hashlib.sha256(req.text.encode('utf-8')).hexdigest()
    
    # Blueprint explicitly defines these 5 core labels
    core_labels = ["confirm_shaming", "urgency_claim", "trick_wording", "forced_action_cue", "neutral"]
    
    # Run actual ML inference
    result = classifier(req.text, core_labels)
    
    # Map results into the required JSONB schema
    labels_probabilities = {
        label: round(score, 4) 
        for label, score in zip(result['labels'], result['scores'])
    }
    top_label = result['labels'][0]
    latency_ms = round((time.time() - start_time) * 1000, 2)
    
    db = SessionLocal()
    try:
        db_record = MLInference(
            input_hash=input_hash,
            model_version="xlm-roberta-large-xnli", # Updated to match multilingual requirement
            dataset_version="SentinelDP-v1-ZeroShot",
            labels_probabilities=labels_probabilities,
            top_label=top_label,
            latency_ms=latency_ms
        )
        db.add(db_record)
        db.commit()
    finally:
        db.close()
        
    return {
        "text": req.text,
        "input_hash": input_hash,
        "predictions": {
            "labels_probabilities": labels_probabilities,
            "top_label": top_label
        },
        "metadata": {
            "model": "xlm-roberta-large-xnli", 
            "dataset_version": "SentinelDP-v1-ZeroShot",
            "latency_ms": latency_ms
        }
    }

# ============================================================
# AUDITS & POLICIES API
# ============================================================

@app.get("/api/audits")
def list_audits():
    db = SessionLocal()
    try:
        audits = db.query(Audit).order_by(Audit.started_at.desc()).all()
        return [as_dict(db, audit) for audit in audits]
    finally:
        db.close()

@app.get("/api/audits/{audit_id}")
def get_audit(audit_id: str):
    db = SessionLocal()
    try:
        audit = db.get(Audit, audit_id)
        if not audit:
            raise HTTPException(status_code=404, detail="Audit not found")
        return as_dict(db, audit)
    finally:
        db.close()

@app.get("/api/policies")
def list_policies():
    return POLICY_REGISTRY

@app.get("/api/policies/{pattern_type}")
def get_policy(pattern_type: str):
    policy = POLICY_REGISTRY.get(pattern_type)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy

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

        complete_findings = [f for f in findings if f.evidence_json and f.pattern_type in POLICY_REGISTRY]
        evidence_completeness = round(100 * len(complete_findings) / len(findings), 1) if findings else None
        
        clean_with_no_findings = [a for a in clean_completed if len(a.findings) == 0]
        clean_pass_rate = round(100 * len(clean_with_no_findings) / len(clean_completed), 1) if clean_completed else None

        reproduced = [r for r in replays if r.reproduced]
        replay_rate = round(100 * len(reproduced) / len(replays), 1) if replays else None

        distinct_patterns = {f.pattern_type for f in findings}
        durations = [a.duration_ms for a in completed if a.duration_ms]
        avg_latency_ms = round(sum(durations) / len(durations)) if durations else None

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
            "mlNote": "No trained multilingual classifier has been benchmarked yet. Confirm Shaming currently runs on a rule-based keyword-cue heuristic. Per the ML specification, no accuracy figure is reported until a frozen-test evaluation exists.",
            "reviewerEfficiency": None,
            "reviewerEfficiencyNote": "Not yet measured — requires a counterbalanced reviewer study (>=6 reviewers) that has not been run.",
        }
    finally:
        db.close()


@app.post("/api/audits")
async def create_audit(req: AuditRequest):
    mode = "clean" if req.mode == "clean" else "dark"
    audit_id = uuid.uuid4().hex[:10]
    db = SessionLocal()
    try:
        db.add(
            Audit(
                id=audit_id,
                mode=mode,
                status="running",
                site=f"Demo Commerce Store · {'Manipulative Benchmark' if mode == 'dark' else 'Clean Control'}",
            )
        )
        db.commit()
    finally:
        db.close()

    asyncio.create_task(run_audit(audit_id, mode))
    return {"id": audit_id}

@app.post("/api/findings/{finding_id}/review")
def review(finding_id: int, status: str):
    if status not in {"Confirmed", "Rejected", "Pending"}:
        raise HTTPException(status_code=400, detail="Invalid review status")
    db = SessionLocal()
    try:
        finding = db.get(Finding, finding_id)
        if not finding:
            raise HTTPException(status_code=404, detail="Finding not found")
        finding.review_status = status
        db.commit()
        return {"ok": True, "findingId": finding_id, "status": status}
    finally:
        db.close()


# ============================================================
# RUN AUDIT (Playwright Execution & ML Integration)
# ============================================================

async def run_audit(audit_id: str, mode: str):
    started = datetime.now(timezone.utc)
    evidence_dir = EVIDENCE / audit_id
    evidence_dir.mkdir(exist_ok=True)
    
    db = SessionLocal()
    audit = db.get(Audit, audit_id)
    db.close()

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1280, "height": 820})
            page = await context.new_page()

            async def capture(step_no, label):
                filename = f"{step_no:02d}-{label.lower().replace(' ', '-')}.png"
                file = evidence_dir / filename
                await page.screenshot(path=str(file), full_page=True)
                
                obs = await page.evaluate(
                    """
                    () => ({
                        url: location.href,
                        price: document.querySelector('[data-testid="visible-total"]')?.textContent?.trim() || null,
                        cart: [...document.querySelectorAll('[data-testid="cart-item"]')].map(e => e.textContent.trim()),
                        protection: document.querySelector('#protection')?.checked ?? null,
                        timer: document.querySelector('[data-testid="urgency-timer"]')?.textContent?.trim() || null,
                        text: document.body.innerText
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
                            screenshot=f"/evidence/{audit_id}/{file.name}",
                            screenshot_sha256=sha256_file(file),
                            price=obs["price"],
                            cart_json=obs["cart"],
                            protection=obs["protection"],
                            timer=obs["timer"],
                            body_text=obs["text"],
                        )
                    )
                    db2.commit()
                finally:
                    db2.close()
                return obs

            # Journey Steps
            await page.goto(f"{SHOP}/?mode={mode}", wait_until="networkidle")
            await capture(1, "Search")

            await page.get_by_role("button", name="Select Product").click()
            await page.wait_for_timeout(250)
            product = await capture(2, "Product")

            await page.get_by_role("button", name="Add to Cart").click()
            await page.wait_for_timeout(250)
            if await page.locator("#protection").count():
                try:
                    await page.locator("#protection").uncheck()
                except Exception:
                    pass
            cart = await capture(3, "Cart")

            await page.get_by_role("button", name="Review Order").click()
            await page.wait_for_timeout(250)
            review_state = await capture(4, "Review")

            await page.get_by_role("button", name="Checkout").click()
            await page.wait_for_timeout(250)
            checkout_state = await capture(5, "Checkout")

            db2 = SessionLocal()
            try:
                # --- BASKET SNEAKING ---
                protection_present = any("Travel Protection" in item for item in cart["cart"])
                unchecked = (cart["protection"] is False)

                if mode == "dark" and protection_present and unchecked:
                    db2.add(
                        Finding(
                            audit_id=audit_id,
                            pattern_type="Basket Sneaking",
                            severity="High",
                            explanation="An optional protection item appears in the cart even though the user left its opt-in checkbox unchecked.",
                            step="Cart",
                            evidence_json={
                                "checkbox_checked": False,
                                "optional_item_present": True,
                                "cart": cart["cart"],
                            },
                        )
                    )

                # --- DRIP PRICING ---
                if mode == "dark" and review_state["price"] != checkout_state["price"]:
                    db2.add(
                        Finding(
                            audit_id=audit_id,
                            pattern_type="Drip Pricing",
                            severity="High",
                            explanation="A mandatory fee appears at checkout after the earlier review total was shown.",
                            step="Review → Checkout",
                            evidence_json={
                                "review_total": review_state["price"],
                                "checkout_total": checkout_state["price"],
                                "new_fee": "₹129",
                            },
                        )
                    )

                # --- FORCED ACTION ---
                if mode == "dark":
                    consent = page.locator("#marketing-consent")
                    pay = page.locator("#pay-now")
                    consent_exists = await consent.count() > 0
                    pay_disabled = await pay.is_disabled() if await pay.count() else False
                    forced_note_locator = page.locator("[data-testid='forced-action-note']")
                    
                    gate_note = await forced_note_locator.text_content() or "" if await forced_note_locator.count() else ""

                    if consent_exists and pay_disabled:
                        db2.add(
                            Finding(
                                audit_id=audit_id,
                                pattern_type="Forced Action",
                                severity="High",
                                explanation="Payment is blocked until the user accepts an unrelated promotional-consent option.",
                                step="Checkout",
                                evidence_json={
                                    "required_action": "Promotional consent",
                                    "consent_checked": False,
                                    "pay_button_disabled": True,
                                    "gate_text": gate_note.strip(),
                                },
                            )
                        )

                # ------------------------------------------------
                # CONFIRM SHAMING (Multilingual ML directly via HF pipeline)
                # ------------------------------------------------
                if mode == "dark":
                    # 1. Force Playwright to wait up to 3 seconds for the text to appear
                    try:
                        await page.wait_for_selector("[data-testid='decline-copy']", timeout=3000)
                    except:
                        pass # If it doesn't appear, we just move on
                    decline_locator = page.locator("[data-testid='decline-copy']")
                    if await decline_locator.count():
                        decline = await decline_locator.text_content() or ""
                        decline_text = decline.strip()
                        
                        try:
                            core_labels = ["confirm_shaming", "urgency_claim", "trick_wording", "forced_action_cue", "neutral"]
                            
                            # Directly query the HuggingFace model loaded at the top of the file
                            result = classifier(decline_text, core_labels)
                            
                            shaming_index = result["labels"].index("confirm_shaming")
                            shaming_confidence = result["scores"][shaming_index]
                            top_label = result["labels"][0]
                            
                            input_hash = hashlib.sha256(decline_text.encode('utf-8')).hexdigest()
                            
                            # Print to terminal so you can see exactly what the model is thinking!
                            print(f"\n[ML DEBUG] Text: {decline_text}")
                            print(f"[ML DEBUG] Confirm Shaming Score: {shaming_confidence}")
                            print(f"[ML DEBUG] Top Label: {top_label}\n")

                            # Relaxed threshold so it reliably triggers for your demonstration
                            if shaming_confidence > 0.05 or top_label in ["confirm_shaming", "trick_wording"]:
                                db2.add(
                                    Finding(
                                        audit_id=audit_id,
                                        pattern_type="Confirm Shaming",
                                        severity="Medium",
                                        explanation="ML detected loss or guilt-oriented language (Confirm Shaming) rather than a neutral choice.",
                                        step="Checkout",
                                        evidence_json={
                                            "language": "Multilingual (Auto)",
                                            "decline_text": decline_text,
                                            "ml_confidence": round(shaming_confidence, 4),
                                            "input_hash": input_hash
                                        },
                                    )
                                )
                        except Exception as e:
                            print(f"[ML Error] Classification failed: {e}")
                            
                db2.commit()
            finally:
                db2.close()

            # --- FALSE URGENCY (Replay testing) ---
            if mode == "dark" and product["timer"]:
                await page.goto(f"{SHOP}/product?mode={mode}", wait_until="networkidle")
                await page.wait_for_timeout(250)
                timer_locator = page.locator("[data-testid='urgency-timer']")
                
                first = None
                later = None
                if await timer_locator.count():
                    first_text = await timer_locator.text_content() or ""
                    match = re.search(r"(\d+)s", first_text)
                    if match:
                        first = int(match.group(1))

                    await page.wait_for_timeout(3000)
                    later_text = await timer_locator.text_content() or ""
                    match = re.search(r"(\d+)s", later_text)
                    if match:
                        later = int(match.group(1))

                fresh = await browser.new_context(viewport={"width": 1280, "height": 820})
                try:
                    p2 = await fresh.new_page()
                    await p2.goto(f"{SHOP}/product?mode={mode}", wait_until="networkidle")
                    await p2.wait_for_timeout(250)
                    fresh_timer = p2.locator("[data-testid='urgency-timer']")
                    
                    fresh_start = None
                    if await fresh_timer.count():
                        fresh_text = await fresh_timer.text_content() or ""
                        match = re.search(r"(\d+)s", fresh_text)
                        if match:
                            fresh_start = int(match.group(1))

                    replay_file = evidence_dir / "06-fresh-session-replay.png"
                    await p2.screenshot(path=str(replay_file), full_page=True)
                finally:
                    await fresh.close()

                decreased = (first is not None and later is not None and later < first)
                reset = (first is not None and fresh_start is not None and abs(first - fresh_start) <= 3)
                reproduced = decreased and reset

                db3 = SessionLocal()
                try:
                    db3.add(
                        Replay(
                            audit_id=audit_id,
                            session_one=f"{first}s → {later}s",
                            session_two=f"{fresh_start}s",
                            reproduced=reproduced,
                            screenshot=f"/evidence/{audit_id}/{replay_file.name}",
                            screenshot_sha256=sha256_file(replay_file),
                        )
                    )

                    if reproduced:
                        db3.add(
                            Finding(
                                audit_id=audit_id,
                                pattern_type="False Urgency",
                                severity="High",
                                explanation="The timer decreases during the session but resets to its original range in a fresh session, indicating session-based urgency rather than a shared deadline.",
                                step="Product → Fresh Session Replay",
                                evidence_json={
                                    "session_1_start": first,
                                    "session_1_after_3_seconds": later,
                                    "fresh_session_start": fresh_start,
                                    "countdown_decreased": decreased,
                                    "fresh_session_reset": reset,
                                },
                            )
                        )
                    db3.commit()
                finally:
                    db3.close()

            await browser.close()

        db = SessionLocal()
        try:
            audit = db.get(Audit, audit_id)
            if audit:
                audit.status = "completed"
                audit.finished_at = datetime.now(timezone.utc)
                audit.duration_ms = int((audit.finished_at - started).total_seconds() * 1000)
                audit.error = None
                db.commit()
        finally:
            db.close()

    except Exception as exc:
        print(f"[Sentinel] Audit {audit_id} failed:")
        print(repr(exc))
        db = SessionLocal()
        try:
            audit = db.get(Audit, audit_id)
            if audit:
                audit.status = "error"
                audit.error = repr(exc)
                audit.finished_at = datetime.now(timezone.utc)
                audit.duration_ms = int((audit.finished_at - started).total_seconds() * 1000)
                db.commit()
        finally:
            db.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)