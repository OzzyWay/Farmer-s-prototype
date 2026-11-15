import { useEffect, useId, useRef, useState } from "react";
import { EXPERT, QUESTIONS, answer, answerTerm, linkFor, matchQuestion, noMatch } from "./answers.js";
import { TERMS } from "../fieldSummary/terms.js";
import ExternalLink from "../landing/ExternalLink.jsx";

/**
 * "Ask about this field": a floating button that opens a small question-and-answer panel.
 * No AI: every answer comes from the rules in answers.js and the data already on the page.
 *
 * Props:
 *   place          { lat, lon, label } or null (the button only shows once a spot is chosen)
 *   rotation       the /api/rotation answer for this place, or null while it loads
 *   rotationState  "ready" | "loading" | "error" | "idle";  rotationError: message when "error"
 *   weather        the useWeather() result ({ status, data })
 */
export default function FieldHelper({ place, rotation, rotationState, rotationError, weather }) {
  const [open, setOpen] = useState(false);
  const [log, setLog] = useState([]); // [{ key, answer }]
  const [typed, setTyped] = useState("");
  const buttonRef = useRef(null);
  const headingRef = useRef(null);
  const bodyRef = useRef(null);
  const counter = useRef(0);
  const id = useId().replace(/:/g, "");

  // A new spot starts a fresh conversation, so old answers never sit under a new place name.
  useEffect(() => {
    setLog([]);
  }, [place?.lat, place?.lon]);

  // Opening moves focus into the panel; Escape closes it and returns focus to the button.
  useEffect(() => {
    if (!open) return undefined;
    headingRef.current?.focus();
    const onKey = (e) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  // Show the newest answer: scroll the panel to it.
  useEffect(() => {
    if (!log.length) return;
    const el = bodyRef.current?.querySelector(`[data-key="${log[log.length - 1].key}"]`);
    el?.scrollIntoView?.({ block: "start" });
  }, [log]);

  if (!place) return null;

  function close() {
    setOpen(false);
    buttonRef.current?.focus();
  }

  const ctx = {
    rotation,
    rotationState,
    rotationError,
    weather: weather?.status === "loaded" ? weather.data : null,
    weatherState: weather?.status === "loaded" ? "ready" : weather?.status === "error" ? "error" : weather?.status === "idle" ? "idle" : "loading",
  };

  function add(a) {
    if (!a) return;
    counter.current += 1;
    setLog((l) => [...l, { key: `a${counter.current}`, answer: a }]);
  }

  function ask(questionId) {
    add(answer(questionId, ctx));
  }

  function submit(e) {
    e.preventDefault();
    const text = typed.trim();
    if (!text) return;
    const m = matchQuestion(text);
    if (!m) add(noMatch(text));
    else if (m.kind === "term") add(answerTerm(m.id));
    else add({ ...answer(m.id, ctx), typed: text });
    setTyped("");
  }

  const groups = [...new Set(QUESTIONS.map((q) => q.group))];

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className={`helper-fab${open ? " is-open" : ""}`}
        aria-expanded={open}
        aria-controls={`${id}-panel`}
        onClick={() => (open ? close() : setOpen(true))}
      >
        <span aria-hidden="true">💬</span> {open ? "Close questions" : "Ask about this field"}
      </button>

      {open && (
        <section id={`${id}-panel`} className="helper-panel" role="dialog" aria-modal="false" aria-labelledby={`${id}-title`}>
          <header className="helper-head">
            <div>
              <h2 id={`${id}-title`} ref={headingRef} tabIndex={-1} className="helper-title">Ask about this field</h2>
              <p className="helper-sub">{place.label} · answers from NASA, USDA and NWS data on this page. No AI.</p>
            </div>
            <button type="button" className="helper-close" onClick={close} aria-label="Close questions">✕</button>
          </header>

          <div className="helper-body" ref={bodyRef}>
            <div role="log" aria-live="polite" aria-relevant="additions" className="helper-log">
              {!log.length && (
                <p className="helper-hint">Tap a question below, or type a few words like "frost" or "flood".</p>
              )}
              {log.map(({ key, answer: a }) => (
                <article key={key} data-key={key} className="helper-turn">
                  <p className="helper-q">{a.typed ? `“${a.typed}” → ${a.question}` : a.question}</p>
                  <div className="helper-a">
                    {a.paragraphs.map((p, i) => <p key={`p${i}`}>{p}</p>)}
                    {a.items.length > 0 && <ul>{a.items.map((t, i) => <li key={`i${i}`}>{t}</li>)}</ul>}
                    {(a.notes || []).map((p, i) => <p key={`n${i}`} className="helper-note">{p}</p>)}
                    {a.terms.length > 0 && (
                      <p className="helper-terms">
                        Words used:{" "}
                        {a.terms.filter((t) => TERMS[t]).map((t, i) => (
                          <button key={t} type="button" className="helper-link-btn" onClick={() => add(answerTerm(t))}>
                            {TERMS[t][0]}{i < a.terms.length - 1 ? "," : ""}
                          </button>
                        ))}
                      </p>
                    )}
                    {a.expert && <p className="helper-expert">{EXPERT}</p>}
                    {a.links.length > 0 && (
                      <ul className="helper-links">
                        {a.links.map((k) => linkFor(k)).filter(Boolean).map((l) => (
                          <li key={l.href}><ExternalLink href={l.href}>{l.label}</ExternalLink></li>
                        ))}
                      </ul>
                    )}
                    {a.sources.length > 0 && <p className="helper-source">Source: {a.sources.join("; ")}</p>}
                  </div>
                </article>
              ))}
            </div>

            <div className="helper-questions">
              {groups.map((g) => (
                <div key={g} className="helper-group" role="group" aria-label={g}>
                  <p className="helper-group-title">{g}</p>
                  <div className="helper-chips">
                    {QUESTIONS.filter((q) => q.group === g).map((q) => {
                      const waiting = (q.needs === "rotation" && ctx.rotationState !== "ready") ||
                        (q.needs === "weather" && ctx.weatherState !== "ready");
                      return (
                        <button key={q.id} type="button" className={`helper-chip${waiting ? " waiting" : ""}`} onClick={() => ask(q.id)}>
                          {q.label}
                          {waiting && <span className="visually-hidden"> (still loading)</span>}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <form className="helper-form" onSubmit={submit}>
            <label htmlFor={`${id}-input`} className="visually-hidden">Type a few words</label>
            <input
              id={`${id}-input`}
              type="text"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder='Type a few words, e.g. "frost"'
              autoComplete="off"
              maxLength={120}
            />
            <button type="submit" className="btn btn-primary">Ask</button>
          </form>
        </section>
      )}
    </>
  );
}
