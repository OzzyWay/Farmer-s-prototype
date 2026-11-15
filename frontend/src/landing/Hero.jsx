import usePrefersReducedMotion from "../farmData/usePrefersReducedMotion.js";
import { hero } from "./copy.js";
import { creditLine } from "./credit.js";
import { scrollToId } from "./scroll.js";

/**
 * The first screen: a field photo (self-hosted, with a plain green background if it fails to
 * load), the page title and two buttons, one into the soil story and one straight to the map.
 */
export default function Hero() {
  const reducedMotion = usePrefersReducedMotion();
  return (
    <section className="hero" aria-labelledby="hero-title">
      <div className="hero-inner">
        <p className="hero-kicker">{hero.kicker}</p>
        <h1 id="hero-title">{hero.title}</h1>
        <p className="hero-lede">{hero.lede}</p>
        <div className="hero-actions">
          <button type="button" className="btn btn-primary landing-btn" onClick={() => scrollToId("depth-story", reducedMotion)}>
            {hero.exploreLabel}
          </button>
          <button type="button" className="btn btn-light landing-btn" onClick={() => scrollToId("map-section", reducedMotion)}>
            {hero.deskLabel}
          </button>
        </div>
      </div>
      <p className="hero-credit">{creditLine()}</p>
    </section>
  );
}
