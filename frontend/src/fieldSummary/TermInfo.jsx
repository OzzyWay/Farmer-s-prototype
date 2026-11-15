import { useEffect, useId, useRef, useState } from "react";

// Plain-language meaning of the terms the findings use (Req 4.7). Keys match the backend's
// "terms" ids in findings.py.
export const TERMS = {
  hot_day: ["Hot day", "A day whose high temperature is above 35 °C (95 °F). Most crops slow down or get stressed above this."],
  warm_night: ["Warm night", "A night whose low stays above 24 °C (75 °F). Plants and animals cannot cool off and recover."],
  frost_day: ["Frost day", "A day whose low is 0 °C (32 °F) or colder. Frost can kill tender plants."],
  clear_change: ["Likely change", "A pattern with less than a 5% chance of being normal ups and downs between years. The test used is called Mann–Kendall."],
  climate_projection: ["Climate outlook", "What climate models suggest over a period of years under one set of emissions assumptions. It shows a range of possible averages, not a prediction for a particular year."],
  hydrologic_group: ["How quickly rain soaks in", "How quickly rain enters wet soil: A is fastest (sandy), D is slowest (heavy clay), so D soils have the most runoff."],
  drainage_class: ["How quickly water drains", "How quickly water leaves the soil after rain. Poorly drained soil keeps roots wet longer."],
  flooding_frequency: ["Flooding frequency", "How often the soil survey expects floods: none, very rare, rare, occasional (about 5 to 50 times in 100 years), frequent or very frequent."],
  k_factor: ["How easily soil washes away", "A measure from about 0.02 (hardly) to 0.69 (very easily). Above about 0.3 means a higher risk of soil washing away."],
  organic_matter: ["Plant and animal material in soil", "The share of the soil made of living and dead plant and animal material. It holds water and nutrients; more is usually better."],
  cover_crop: ["Cover crop", "A crop grown mainly to protect and feed the soil between cash crops, not for sale."],
  variation: ["Year-to-year changes", "How much a value swings from one year to the next, shown as a percentage of its average."],
  ndvi: ["Greenness score", "How green the ground looks from space, from about 0.1 (bare soil) to 0.9 (thick growing plants). Below 0.25 counts as bare here."],
  soil_wetness: ["Soil wetness near roots", "How wet the soil is where roots grow, from 0 (dry) to 1 (full of water), based on NASA's model."],
};

/**
 * A small "?" button next to a term. Pressing it (mouse, touch, Enter or Space) shows a short
 * explanation; Escape or clicking elsewhere closes it, and focus returns to the button.
 */
export default function TermInfo({ term }) {
  const entry = TERMS[term];
  const [open, setOpen] = useState(false);
  const id = useId().replace(/:/g, "");
  const wrap = useRef(null);
  const button = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    const onClick = (e) => {
      if (!wrap.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onClick);
    };
  }, [open]);

  if (!entry) return null;
  const [name, text] = entry;
  return (
    <span className="term" ref={wrap}>
      <button
        ref={button}
        type="button"
        className="term-btn"
        aria-expanded={open}
        aria-controls={`${id}-tip`}
        onClick={() => setOpen((o) => !o)}
      >
        {name}
        <span className="term-q" aria-hidden="true">?</span>
      </button>
      {open && (
        <span id={`${id}-tip`} className="term-tip" role="note">
          {text}
        </span>
      )}
    </span>
  );
}
