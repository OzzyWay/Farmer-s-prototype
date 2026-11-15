import { DIMENSIONS } from "./labels.js";

/**
 * The six 0-100 scores as bars, the overall score, and "How was this scored?" with every part
 * of each formula. Priority scores (weight 2) are marked "counts double".
 *
 * scores: { today: {water, soil, ..., overall}, outlook: {...} | null }
 * parts:  { water: [{label, points}], ... }
 * weights: { water: 1 | 2, ... }
 */
export default function ScoreBars({ scores, parts, weights }) {
  const today = scores?.today;
  if (!today) return <p className="small-print">No scores: we could not tell what grows here.</p>;
  const outlook = scores.outlook;
  return (
    <div className="scores">
      <ul className="score-list">
        {DIMENSIONS.map((d) => (
          <li key={d.id} className="score-row">
            <span className="score-label">
              {d.label}
              {weights?.[d.id] === 2 && <span className="double"> · counts double</span>}
            </span>
            <span className="score-bar" aria-hidden="true">
              <span className="score-fill" style={{ width: `${today[d.id]}%` }} />
            </span>
            <span className="score-num">
              {today[d.id]}
              <span className="visually-hidden"> out of 100</span>
            </span>
          </li>
        ))}
      </ul>
      <details className="details">
        <summary>How was this scored?</summary>
        <p className="small-print">
          Each score is 0 to 100, built from the crop table and this field's facts. It compares options for this
          field; it is not a yield forecast. Overall is the average, with your priorities counted twice.
          {outlook && " The 2030-2049 score uses the projected climate and takes 15 points off for each crop at future risk."}
        </p>
        {DIMENSIONS.map((d) => (
          <div key={d.id} className="score-parts">
            <h5>{d.label}: {today[d.id]}{outlook && ` (2030-2049: ${outlook[d.id]})`}</h5>
            <p className="small-print">{d.help}</p>
            <ul>
              {(parts?.[d.id] || []).map((p, i) => (
                <li key={i}>
                  {p.label} <span className="points">{p.points > 0 && i > 0 ? "+" : ""}{p.points}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </details>
    </div>
  );
}
