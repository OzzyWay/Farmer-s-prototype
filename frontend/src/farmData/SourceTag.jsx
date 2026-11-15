import { formatFreshness, formatResolution } from "./format.js";

/**
 * Small label saying where a group of facts came from, how coarse it is, and whether
 * it was fetched just now or read from the backend's saved copy.
 * Example: "NASA POWER · 50 km resolution · live"
 */
export default function SourceTag({ records }) {
  if (!records?.length) return null;
  const first = records[0];
  const freshness = [...new Set(records.map((r) => formatFreshness(r.live_or_cached)))].join(" and ");
  return (
    <p className="source-tag">
      <span>Source: {first.source}</span>
      <span aria-hidden="true">·</span>
      <span>{formatResolution(first.resolution_m)} resolution</span>
      <span aria-hidden="true">·</span>
      <span>{freshness}</span>
    </p>
  );
}
