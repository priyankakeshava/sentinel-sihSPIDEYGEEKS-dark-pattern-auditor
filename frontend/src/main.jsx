import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const API = "http://127.0.0.1:8000";

const NAV = [
  ["console", "Investigation Console"],
  ["journey", "Journey Evidence"],
  ["replay", "Replay Verification"],
  ["review", "Review Queue"],
];

function App() {
  const [audits, setAudits] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [running, setRunning] = useState(false);
  const [health, setHealth] = useState(null);
  const [view, setView] = useState("console");

  async function load() {
    const h = await fetch(API + "/api/health")
      .then((r) => r.json())
      .catch(() => null);

    setHealth(h);

    const rows = await fetch(API + "/api/audits")
      .then((r) => r.json())
      .catch(() => []);

    setAudits(rows);

    if (!selectedId && rows[0]) {
      setSelectedId(rows[0].id);
    }
  }

  useEffect(() => {
    load();

    const timer = setInterval(load, 1200);

    return () => clearInterval(timer);
  }, []);

  async function run(mode) {
    setRunning(true);

    try {
      const res = await fetch(API + "/api/audits", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ mode }),
      });

      if (!res.ok) {
        throw new Error("Unable to start audit");
      }

      const { id } = await res.json();

      setSelectedId(id);

      let done = false;

      while (!done) {
        await new Promise((resolve) => setTimeout(resolve, 900));

        const a = await fetch(API + "/api/audits/" + id).then((r) =>
          r.json()
        );

        setSelectedId(a.id);

        done = a.status === "completed" || a.status === "error";
      }

      await load();
    } catch (error) {
      console.error("Audit failed:", error);
      await load();
    } finally {
      setRunning(false);
    }
  }

  async function review(id, status) {
    try {
      const res = await fetch(
        API +
          "/api/findings/" +
          id +
          "/review?status=" +
          encodeURIComponent(status),
        {
          method: "POST",
        }
      );

      if (!res.ok) {
        throw new Error("Unable to update finding");
      }

      await load();
    } catch (error) {
      console.error("Review update failed:", error);
    }
  }

  const findings = audits.reduce(
    (total, audit) => total + audit.findings.length,
    0
  );

  const confirmed = audits.reduce(
    (total, audit) =>
      total +
      audit.findings.filter((f) => f.reviewStatus === "Confirmed").length,
    0
  );

  const pending = audits.reduce(
    (total, audit) =>
      total +
      audit.findings.filter(
        (f) => !f.reviewStatus || f.reviewStatus === "Pending"
      ).length,
    0
  );

  const selected =
    audits.find((audit) => audit.id === selectedId) || audits[0] || null;

  function selectAudit(id) {
    const audit = audits.find((item) => item.id === id);

    if (audit) {
      setSelectedId(audit.id);
    }
  }

  /*
   * IMPORTANT:
   * View Audit must select the audit AND navigate somewhere.
   *
   * Previously it only called selectAudit(), which changed selectedId
   * while the user stayed on Review Queue.
   */
  function viewAudit(id) {
    const audit = audits.find((item) => item.id === id);

    if (!audit) {
      return;
    }

    setSelectedId(audit.id);

    // Open the complete evidence for this audit.
    setView("journey");
  }

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <div className="shield">S</div>

          <div>
            <b>SENTINEL</b>
            <span>Government Dark Pattern Investigation Console</span>
          </div>
        </div>

        <div className="connection">
          <i className={health ? "on" : ""}></i>

          {health ? "Backend connected" : "Backend offline"}
        </div>
      </header>

      <div className="layout">
        <aside>
          {NAV.map(([key, label]) => (
            <button
              key={key}
              className={"nav " + (view === key ? "active" : "")}
              onClick={() => setView(key)}
            >
              {label}
            </button>
          ))}

          <div className="note">
            <b>Human-in-the-loop</b>
            <br />
            Sentinel produces risk evidence, not a legal verdict.
          </div>

          <div className="stack">
            <span>PLAYWRIGHT</span>
            <span>FASTAPI</span>
            <span>MYSQL</span>
          </div>
        </aside>

        <main>
          {view === "console" && (
            <ConsoleView
              audits={audits}
              selected={selected}
              running={running}
              health={health}
              findings={findings}
              confirmed={confirmed}
              review={review}
              run={run}
            />
          )}

          {view === "journey" && (
            <JourneyView
              audits={audits}
              selected={selected}
              onSelect={selectAudit}
            />
          )}

          {view === "replay" && (
            <ReplayView
              audits={audits}
              selected={selected}
              onSelect={selectAudit}
            />
          )}

          {view === "review" && (
            <ReviewQueue
              audits={audits}
              pending={pending}
              review={review}
              onSelect={selectAudit}
              onViewAudit={viewAudit}
            />
          )}
        </main>
      </div>
    </div>
  );
}

function ConsoleView({
  audits,
  selected,
  running,
  health,
  findings,
  confirmed,
  review,
  run,
}) {
  return (
    <>
      <div className="hero">
        <div>
          <div className="eyebrow">SENTINEL · CORE ENGINE</div>

          <h1>Journey-level regulatory audit</h1>

          <p>
            Simulate a consumer journey, verify suspicious behaviour and
            package reproducible evidence for human review.
          </p>
        </div>

        <div className="actions">
          <button
            className="primary"
            disabled={running}
            onClick={() => run("dark")}
          >
            {running ? "Running audit…" : "▶ Run Manipulative Audit"}
          </button>

          <button
            className="control"
            disabled={running}
            onClick={() => run("clean")}
          >
            ✓ Run Clean Control
          </button>
        </div>
      </div>

      <div className="metrics">
        <Metric label="Audits" value={audits.length} />

        <Metric label="Potential findings" value={findings} />

        <Metric label="Confirmed by reviewer" value={confirmed} />

        <Metric
          label="Evidence store"
          value={
            health?.database === "mysql"
              ? "MySQL"
              : health?.database === "sqlite"
              ? "SQLite fallback"
              : health?.database || "Unavailable"
          }
        />
      </div>

      {!selected ? (
        <div className="empty">
          <div className="big">◈</div>

          <h2>Ready for investigation</h2>

          <p>
            Run the manipulative benchmark to watch Sentinel perform Search →
            Product → Cart → Review → Checkout.
          </p>
        </div>
      ) : (
        <Audit audit={selected} review={review} />
      )}
    </>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Audit({ audit, review, only }) {
  if (only === "journey") {
    return <JourneySection audit={audit} />;
  }

  if (only === "replay") {
    return <ReplaySection audit={audit} />;
  }

  return (
    <div className="audit">
      <AuditSummary audit={audit} />

      <JourneySection audit={audit} />

      {audit.replay && <ReplaySection audit={audit} />}

      <FindingsSection audit={audit} review={review} />
    </div>
  );
}

function AuditSummary({ audit }) {
  return (
    <section className="panel summary">
      <div>
        <div className="eyebrow">AUDIT {audit.id}</div>

        <h2>{audit.site}</h2>

        <p>
          {audit.status === "running"
            ? "Browser journey in progress…"
            : "Journey complete · " +
              ((audit.durationMs || 0) / 1000).toFixed(1) +
              "s"}
        </p>
      </div>

      <div className={"pill " + audit.status}>{audit.status}</div>
    </section>
  );
}

function JourneySection({ audit }) {
  return (
    <section className="panel">
      <div className="sectionHead">
        <div>
          <h3>1 · Automated Journey</h3>
          <span>Real browser actions + captured state</span>
        </div>

        <span className="tag">PLAYWRIGHT</span>
      </div>

      {audit.steps?.length ? (
        <div className="journey">
          {audit.steps.map((step) => (
            <div className="journeyCard" key={step.step}>
              <div className="stepTop">
                <b>{String(step.step).padStart(2, "0")}</b>

                <span>{step.label}</span>
              </div>

              <img src={API + step.screenshot} alt={step.label} />

              <div className="state">
                <span>Price</span>
                <b>{step.price || "—"}</b>
              </div>

              <div className="state">
                <span>Cart items</span>
                <b>{step.cart.length}</b>
              </div>

              <div
                className="hash"
                title={step.screenshotSha256 || ""}
              >
                SHA-256 {step.screenshotSha256?.slice(0, 12)}…
              </div>

              {step.timer && (
                <div className="timerState">⏱ {step.timer}</div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="empty compact">
          Journey data is still being captured.
        </div>
      )}

      <div className="subpanel graphPanel">
        <div className="sectionHead">
          <div>
            <h3>2 · Journey Evidence Graph</h3>
            <span>Connects actions, state changes and findings</span>
          </div>

          <span className="tag blue">EVIDENCE</span>
        </div>

        {audit.graph?.nodes ? (
          <>
            <div className="graph">
              {audit.graph.nodes
                .filter((node) => node.type === "journey")
                .map((node, index, journeyNodes) => (
                  <React.Fragment key={node.id}>
                    <div className="node journeyNode">
                      <b>{node.label}</b>
                      <small>captured</small>
                    </div>

                    {index < journeyNodes.length - 1 && (
                      <div className="arrow">→</div>
                    )}
                  </React.Fragment>
                ))}
            </div>

            <div className="findingLinks">
              {audit.graph.nodes
                .filter((node) => node.type === "finding")
                .map((node) => (
                  <span key={node.id}>↳ {node.label}</span>
                ))}
            </div>
          </>
        ) : (
          <div className="empty compact">
            Evidence graph is not available yet.
          </div>
        )}
      </div>
    </section>
  );
}

function ReplaySection({ audit }) {
  if (!audit.replay) {
    return (
      <section className="panel">
        <div className="empty compact">
          No replay verification is available for this audit.
        </div>
      </section>
    );
  }

  return (
    <section className="panel replayPanel">
      <div className="sectionHead">
        <div>
          <h3>3 · Behavioural Verification</h3>

          <span>Fresh-session replay of suspicious timer behaviour</span>
        </div>

        <span
          className={
            "tag " + (audit.replay.reproduced ? "red" : "green")
          }
        >
          {audit.replay.reproduced ? "REPRODUCED" : "NOT REPRODUCED"}
        </span>
      </div>

      <div className="replayGrid">
        <div>
          <small>Session 1</small>

          <b>{audit.replay.session1}</b>

          <span>countdown observed</span>
        </div>

        <div className="replayArrow">↻</div>

        <div>
          <small>Fresh browser session</small>

          <b>{audit.replay.session2}</b>

          <span>starting value checked</span>
        </div>

        <div>
          {audit.replay.screenshot && (
            <img
              src={API + audit.replay.screenshot}
              alt="Fresh session replay"
            />
          )}

          <div
            className="hash"
            title={audit.replay.screenshotSha256 || ""}
          >
            SHA-256 {audit.replay.screenshotSha256?.slice(0, 12)}…
          </div>
        </div>
      </div>
    </section>
  );
}

function FindingsSection({ audit, review }) {
  return (
    <section className="panel">
      <div className="sectionHead">
        <div>
          <h3>4 · Evidence Findings</h3>

          <span>Risk signals prepared for human regulatory review</span>
        </div>

        <span className="tag">HUMAN REVIEW</span>
      </div>

      {audit.findings.length === 0 ? (
        <div className="cleanResult">
          ✓ No suspicious pattern detected in this control journey.
        </div>
      ) : (
        <div className="findings">
          {audit.findings.map((finding) => (
            <Finding
              key={finding.id}
              f={finding}
              review={review}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function Finding({ f, review }) {
  const status = f.reviewStatus || "Pending";

  const decided =
    status === "Confirmed" || status === "Rejected";

  return (
    <article className="finding">
      <div className="findingHead">
        <div>
          <span className="category">DARK PATTERN SIGNAL</span>

          <h3>{f.type}</h3>
        </div>

        <span
          className={
            "severity " + f.severity.toLowerCase()
          }
        >
          {f.severity}
        </span>
      </div>

      <p>{f.explanation}</p>

      <div className="evidenceBox">
        <div>
          <span>Journey location</span>
          <b>{f.step}</b>
        </div>

        {Object.entries(f.evidence || {}).map(([key, value]) => (
          <div key={key}>
            <span>{key.replaceAll("_", " ")}</span>

            <b>
              {typeof value === "object"
                ? JSON.stringify(value)
                : String(value)}
            </b>
          </div>
        ))}
      </div>

      <div className="reviewRow">
        {!decided ? (
          <>
            <button
              className="confirm"
              onClick={() => review(f.id, "Confirmed")}
            >
              Confirm finding
            </button>

            <button
              className="reject"
              onClick={() => review(f.id, "Rejected")}
            >
              Reject
            </button>

            <span className="reviewStatus pendingStatus">
              Pending
            </span>
          </>
        ) : (
          <>
            <span
              className={
                "reviewStatus " +
                (status === "Confirmed"
                  ? "confirmedStatus"
                  : "rejectedStatus")
              }
            >
              {status === "Confirmed"
                ? "✓ Confirmed"
                : "✕ Rejected"}
            </span>

            <button
              className="editReview"
              onClick={() => review(f.id, "Pending")}
            >
              Edit review
            </button>
          </>
        )}
      </div>
    </article>
  );
}

function PageHeader({ eyebrow, title, description }) {
  return (
    <div className="pageHeader">
      <div className="eyebrow">{eyebrow}</div>

      <h1>{title}</h1>

      <p>{description}</p>
    </div>
  );
}

function AuditPicker({ audits, selected, onSelect }) {
  if (!audits.length) {
    return null;
  }

  return (
    <div className="auditPicker">
      <span>Audit</span>

      <select
        value={selected?.id || ""}
        onChange={(event) => onSelect(event.target.value)}
      >
        {audits.map((audit) => (
          <option value={audit.id} key={audit.id}>
            {audit.id} · {audit.mode} · {audit.status}
          </option>
        ))}
      </select>
    </div>
  );
}

function JourneyView({ audits, selected, onSelect }) {
  return (
    <>
      <PageHeader
        eyebrow="SENTINEL · EVIDENCE"
        title="Journey Evidence"
        description="Review the captured browser journey, screenshots, state changes and evidence graph for each audit."
      />

      {selected && (
        <AuditPicker
          audits={audits}
          selected={selected}
          onSelect={onSelect}
        />
      )}

      {selected ? (
        <Audit audit={selected} only="journey" />
      ) : (
        <div className="empty">
          <h2>No audits yet</h2>

          <p>
            Run an audit from the Investigation Console first.
          </p>
        </div>
      )}
    </>
  );
}

function ReplayView({ audits, selected, onSelect }) {
  const replayAudits = audits.filter(
    (audit) => audit.replay
  );

  const current =
    selected?.replay
      ? selected
      : replayAudits[0] || null;

  return (
    <>
      <PageHeader
        eyebrow="SENTINEL · VERIFICATION"
        title="Replay Verification"
        description="Check whether suspicious behaviour can be reproduced in a fresh isolated browser session."
      />

      {replayAudits.length > 0 && current && (
        <AuditPicker
          audits={replayAudits}
          selected={current}
          onSelect={onSelect}
        />
      )}

      {current ? (
        <Audit audit={current} only="replay" />
      ) : (
        <div className="empty">
          <h2>No replay evidence yet</h2>

          <p>
            Run a manipulative audit to generate fresh-session
            replay evidence.
          </p>
        </div>
      )}
    </>
  );
}

function ReviewQueue({
  audits,
  pending,
  review,
  onSelect,
  onViewAudit,
}) {
  const queue = useMemo(
    () =>
      audits.flatMap((audit) =>
        audit.findings
          .filter(
            (finding) =>
              !finding.reviewStatus ||
              finding.reviewStatus === "Pending"
          )
          .map((finding) => ({
            ...finding,
            audit,
          }))
      ),
    [audits]
  );

  return (
    <>
      <PageHeader
        eyebrow="SENTINEL · HUMAN REVIEW"
        title="Review Queue"
        description="Only findings awaiting a human decision are shown here. Confirmed and rejected findings are removed from the pending queue."
      />

      <div className="queueMetric">
        <strong>{pending}</strong>

        <span>
          finding{pending === 1 ? "" : "s"} pending review
        </span>
      </div>

      {queue.length === 0 ? (
        <div className="empty">
          <div className="big">✓</div>

          <h2>Review queue is clear</h2>

          <p>
            There are no pending findings requiring a human
            decision.
          </p>
        </div>
      ) : (
        <div className="queue">
          {queue.map((item) => (
            <article
              className="queueItem"
              key={item.audit.id + "-" + item.id}
            >
              <div className="queueTop">
                <div>
                  <span className="category">
                    {item.audit.id} ·{" "}
                    {item.audit.mode.toUpperCase()}
                  </span>

                  <h2>{item.type}</h2>
                </div>

                <span
                  className={
                    "severity " +
                    item.severity.toLowerCase()
                  }
                >
                  {item.severity}
                </span>
              </div>

              <p>{item.explanation}</p>

              <div className="queueMeta">
                <span>Journey location</span>

                <b>{item.step}</b>
              </div>

              <div className="reviewRow">
                <button
                  className="confirm"
                  onClick={() =>
                    reviewFromQueue(
                      item,
                      review,
                      onSelect,
                      "Confirmed"
                    )
                  }
                >
                  Confirm finding
                </button>

                <button
                  className="reject"
                  onClick={() =>
                    reviewFromQueue(
                      item,
                      review,
                      onSelect,
                      "Rejected"
                    )
                  }
                >
                  Reject
                </button>

                {/* FIXED:
                    Previously this only called onSelect().
                    That changed the audit but did not change the page.
                    It now navigates to Journey Evidence. */}
                <button
                  className="viewAudit"
                  onClick={() => onViewAudit(item.audit.id)}
                >
                  View audit
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  );
}

async function reviewFromQueue(
  item,
  review,
  onSelect,
  status
) {
  await review(item.id, status);

  /*
   * Keep the audit selected after reviewing.
   * The queue itself will automatically refresh because
   * review() calls load().
   */
  onSelect(item.audit.id);
}

createRoot(document.getElementById("root")).render(
  <App />
);