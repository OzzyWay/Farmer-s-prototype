import { LINKS, dataLimitations } from "../landing/copy.js";
import ExternalLink from "../landing/ExternalLink.jsx";

/**
 * Every data source with its resolution and licence, and what the results can and cannot say.
 * outlook: the outlook part of the /api/rotation answer (to name the models when loaded)
 */
export default function DataLimitations({ outlook }) {
  const models = outlook?.status === "ok" ? outlook.models?.join(", ") : null;
  return (
    <section className="summary-card limits" aria-labelledby="limits-h">
      <h3 id="limits-h" className="card-title">Data and limitations</h3>
      <ul className="limits-list">
        <li>
          <strong>Crop table written for Central Texas.</strong> The 15 crops, their months and limits come from SARE,
          USDA NRCS plant guides and Texas A&amp;M AgriLife Extension, written for Central Texas. Elsewhere in the US,
          treat the options as rough ideas.
        </li>
        <li>
          <strong>Estimated field area.</strong> The yellow box on the map is about 1 km around the point you chose.
          It is not your field boundary.
        </li>
        <li>
          <strong>USDA NASS Cropland Data Layer, 30 m.</strong> What grew on one 30 m square each year, read from
          satellite images. One square can be mislabelled (for example a tree line read as forest). Public domain.
        </li>
        <li>
          <strong>USDA NRCS SSURGO soil survey.</strong> Averages for a mapped soil area (often several hectares), not a
          test of your field. Public domain.
        </li>
        <li>
          <strong>NASA POWER, about 50 km.</strong> Daily weather since 1981 from NASA's models and satellites. It
          describes the regional climate, not your field. Trends use the Theil–Sen slope and the Mann–Kendall test;
          "clear" means p &lt; 0.05. Free to use, credit NASA Langley POWER.
        </li>
        <li>
          <strong>2030–2049 outlook, Open-Meteo Climate API, about 10 km.</strong> The change from 1991–2020 in{" "}
          {models || "three climate models"} under a high-emissions scenario, added to the NASA POWER averages. A range
          of possible futures, not a forecast. Weather data by{" "}
          <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Open-Meteo.com</a>, licensed{" "}
          <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a>.
        </li>
        <li>
          <strong>Scores are a guide, not a yield model.</strong> They come from the crop table's low / medium / high
          values and the field facts, with every formula shown under "How was this scored?". There are no prices,
          equipment or labour data.
        </li>
        <li>
          <strong>Map.</strong> Basemap © OpenStreetMap contributors via OpenFreeMap; terrain from Mapzen terrain
          tiles on AWS.
        </li>
        <li>
          <strong>Weather.</strong> The 7-day forecast and official alerts come from the National Weather Service
          (US only). Farm alerts are worked out from the next 3 days of that forecast and are suggestions.
        </li>
        <li>
          <strong>Photo and fonts.</strong> Hero photo by Federico Respini on Unsplash (Unsplash License). Fraunces
          and Inter fonts under the SIL Open Font License. All are served from this site.
        </li>
      </ul>
      <p className="small-print">{dataLimitations.helpLead}</p>
      <ul className="help-links">
        <li><ExternalLink href={LINKS.extension.href}>{LINKS.extension.label}</ExternalLink></li>
        <li><ExternalLink href={LINKS.nrcs.href}>{LINKS.nrcs.label}</ExternalLink></li>
        <li><ExternalLink href={LINKS.serviceCenter.href}>{LINKS.serviceCenter.label}</ExternalLink></li>
      </ul>
      <p className="small-print">
        This tool supports your judgment as a farmer. It does not replace it, or your county extension agent.
      </p>
    </section>
  );
}
