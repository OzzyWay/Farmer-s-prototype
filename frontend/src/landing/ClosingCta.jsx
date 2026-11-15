import usePrefersReducedMotion from "../farmData/usePrefersReducedMotion.js";
import { LINKS, closingCta } from "./copy.js";
import ExternalLink from "./ExternalLink.jsx";
import { scrollToId } from "./scroll.js";

/** End of the page: back to the map, and where to find a person to talk to. */
export default function ClosingCta() {
  const reducedMotion = usePrefersReducedMotion();
  return (
    <section id="closing-cta" className="landing-section closing-cta" aria-labelledby="closing-title">
      <div className="landing-inner">
        <h2 id="closing-title">{closingCta.heading}</h2>
        <p className="landing-lede">{closingCta.text}</p>
        <button type="button" className="btn btn-primary landing-btn" onClick={() => scrollToId("map-section", reducedMotion)}>
          {closingCta.buttonLabel}
        </button>
        <div className="closing-help">
          <p>{closingCta.helpLead}</p>
          <ul className="help-links">
            <li><ExternalLink href={LINKS.extension.href}>{LINKS.extension.label}</ExternalLink></li>
            <li><ExternalLink href={LINKS.nrcs.href}>{LINKS.nrcs.label}</ExternalLink></li>
          </ul>
        </div>
      </div>
    </section>
  );
}
