const CARD_VERSION = 1;

const CSS = `
  :host {
    --bft-bg: var(--ha-card-background, var(--card-background-color, #fff));
    --bft-text: var(--primary-text-color, #333);
    --bft-secondary: var(--secondary-text-color, #666);
    --bft-border: var(--divider-color, #e0e0e0);
    --bft-empty: var(--disabled-text-color, #bbb);
    --bft-low: #e53935;
  }
  ha-card {
    padding: 16px;
  }
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }
  .header .title {
    font-size: 16px;
    font-weight: 500;
    color: var(--bft-text);
  }
  .header .total {
    font-size: 13px;
    color: var(--bft-secondary);
  }
  .trays {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .tray {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .tray.empty {
    opacity: 0.4;
  }
  .color-dot {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    flex-shrink: 0;
    border: 2px solid var(--bft-border);
  }
  .tray-info {
    flex: 1;
    min-width: 0;
  }
  .tray-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
  }
  .tray-label {
    font-size: 13px;
    font-weight: 500;
    color: var(--bft-text);
  }
  .tray-material {
    font-size: 12px;
    color: var(--bft-secondary);
  }
  .bar-bg {
    width: 100%;
    height: 8px;
    border-radius: 4px;
    background: var(--bft-border);
    overflow: hidden;
  }
  .bar-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.5s ease;
  }
  .bar-fill.low {
    animation: pulse-low 1.5s ease-in-out infinite;
  }
  @keyframes pulse-low {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
  .tray-bottom {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 3px;
  }
  .tray-color-hex {
    font-size: 11px;
    color: var(--bft-secondary);
    font-family: monospace;
  }
  .tray-weight {
    font-size: 11px;
    color: var(--bft-secondary);
  }
  .footer {
    display: flex;
    justify-content: space-between;
    margin-top: 16px;
    padding-top: 12px;
    border-top: 1px solid var(--bft-border);
    font-size: 12px;
    color: var(--bft-secondary);
  }
`;

class BambuFilamentTrackerCard extends HTMLElement {
  static get version() { return CARD_VERSION; }

  set hass(hass) {
    this._hass = hass;
    this._updateCard();
  }

  setConfig(config) {
    this._config = config;
    this._prefix = config.entity_prefix || "filament_tracker";
    this._showEmpty = config.show_empty_trays !== false;
    this._showTotals = config.show_totals !== false;
  }

  connectedCallback() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
  }

  _updateCard() {
    if (!this._hass || !this.shadowRoot) return;

    const trays = [];
    for (let i = 1; i <= 4; i++) {
      const remaining = this._hass.states[`sensor.${this._prefix}_tray_${i}_remaining`];
      const pct = this._hass.states[`sensor.${this._prefix}_tray_${i}_remaining_pct`];
      const color = this._hass.states[`sensor.${this._prefix}_tray_${i}_color`];
      const material = this._hass.states[`sensor.${this._prefix}_tray_${i}_material`];
      const low = this._hass.states[`binary_sensor.${this._prefix}_tray_${i}_low`];

      const isEmpty = !remaining || remaining.state === "unknown" || remaining.state === "unavailable" || remaining.state === "None";
      const colorHex = (color && color.state && color.state !== "unknown" && color.state !== "None") ? color.state : "#cccccc";
      const materialStr = (material && material.state && material.state !== "unknown" && material.state !== "None") ? material.state : "";
      const pctVal = (!isEmpty && pct && pct.state !== "unknown") ? parseInt(pct.state) : 0;
      const remainingVal = !isEmpty ? parseFloat(remaining.state) : 0;
      const initialVal = (!isEmpty && remaining.attributes && remaining.attributes.initial_weight_g) ? remaining.attributes.initial_weight_g : 1000;
      const isLow = low && low.state === "on";

      trays.push({ i, isEmpty, colorHex, materialStr, pctVal, remainingVal, initialVal, isLow });
    }

    const totalEntity = this._hass.states[`sensor.${this._prefix}_total_consumed`];
    const lastPrintEntity = this._hass.states[`sensor.${this._prefix}_last_print_usage`];
    const totalVal = totalEntity ? parseFloat(totalEntity.state) || 0 : 0;
    const lastPrintVal = lastPrintEntity ? parseFloat(lastPrintEntity.state) || 0 : 0;

    const trayHtml = trays
      .filter(t => this._showEmpty || !t.isEmpty)
      .map(t => {
        if (t.isEmpty) {
          return `
            <div class="tray empty">
              <div class="color-dot" style="background: var(--bft-empty);"></div>
              <div class="tray-info">
                <div class="tray-top">
                  <span class="tray-label">Tray ${t.i}</span>
                  <span class="tray-material">Empty</span>
                </div>
                <div class="bar-bg"><div class="bar-fill" style="width: 0%;"></div></div>
              </div>
            </div>`;
        }
        const barColor = t.isLow ? "var(--bft-low)" : t.colorHex;
        const lowClass = t.isLow ? " low" : "";
        return `
          <div class="tray">
            <div class="color-dot" style="background: ${t.colorHex};"></div>
            <div class="tray-info">
              <div class="tray-top">
                <span class="tray-label">Tray ${t.i} &mdash; ${t.pctVal}%</span>
                <span class="tray-material">${t.materialStr}</span>
              </div>
              <div class="bar-bg">
                <div class="bar-fill${lowClass}" style="width: ${t.pctVal}%; background: ${barColor};"></div>
              </div>
              <div class="tray-bottom">
                <span class="tray-color-hex">${t.colorHex}</span>
                <span class="tray-weight">${t.remainingVal}g / ${t.initialVal}g</span>
              </div>
            </div>
          </div>`;
      })
      .join("");

    const footerHtml = this._showTotals
      ? `<div class="footer">
           <span>Last print: ${lastPrintVal.toFixed(1)}g</span>
           <span>Lifetime: ${this._formatWeight(totalVal)}</span>
         </div>`
      : "";

    this.shadowRoot.innerHTML = `
      <style>${CSS}</style>
      <ha-card>
        <div class="header">
          <span class="title">Filament Tracker</span>
          <span class="total">${this._formatWeight(totalVal)} total</span>
        </div>
        <div class="trays">${trayHtml}</div>
        ${footerHtml}
      </ha-card>
    `;
  }

  _formatWeight(g) {
    if (g >= 1000) {
      return (g / 1000).toFixed(2) + "kg";
    }
    return g.toFixed(1) + "g";
  }

  static getStubConfig() {
    return { entity_prefix: "filament_tracker", show_empty_trays: true, show_totals: true };
  }

  getCardSize() {
    return 4;
  }
}

customElements.define("bambu-filament-tracker-card", BambuFilamentTrackerCard);

console.info(
  "%c BAMBU-FILAMENT-TRACKER %c v" + CARD_VERSION + " ",
  "background:#4CAF50;color:white;font-weight:bold",
  "background:#333;color:white"
);
