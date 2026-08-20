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