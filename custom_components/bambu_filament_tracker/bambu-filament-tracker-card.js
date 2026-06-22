const CARD_VERSION = 3;

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
  .section-label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--bft-secondary);
    margin: 16px 0 8px 0;
    padding-bottom: 4px;
    border-bottom: 1px solid var(--bft-border);
  }
  .section-label:first-of-type {
    margin-top: 0;
  }
  .filaments {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .filament {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .filament.stored {
    opacity: 0.7;
  }
  .filament.empty-spool {
    opacity: 0.4;
  }
  .color-dot {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    flex-shrink: 0;
    border: 2px solid var(--bft-border);
  }
  .filament-info {
    flex: 1;
    min-width: 0;
  }
  .filament-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
  }
  .filament-label {
    font-size: 13px;
    font-weight: 500;
    color: var(--bft-text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 60%;
  }
  .filament-type {
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
  .filament-bottom {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 3px;
  }
  .filament-status {
    font-size: 11px;
    color: var(--bft-secondary);
  }
  .filament-weight {
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
  .no-filaments {
    text-align: center;
    color: var(--bft-secondary);
    font-size: 13px;
    padding: 24px 0;
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
    this._showStored = config.show_stored !== false;
    this._showEmpty = config.show_empty !== false;
    this._showTotals = config.show_totals !== false;
  }

  connectedCallback() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
  }

  _updateCard() {
    if (!this._hass || !this.shadowRoot) return;

    const filaments = this._findFilamentEntities();
    const loaded = filaments.filter(f => f.isLoaded);
    const stored = filaments.filter(f => !f.isLoaded && f.remaining > 0);
    const empty = filaments.filter(f => !f.isLoaded && f.remaining <= 0);

    const totalEntity = this._hass.states[`sensor.${this._prefix}_total_consumed`];
    const lastPrintEntity = this._hass.states[`sensor.${this._prefix}_last_print_usage`];
    const totalVal = totalEntity ? parseFloat(totalEntity.state) || 0 : 0;
    const lastPrintVal = lastPrintEntity ? parseFloat(lastPrintEntity.state) || 0 : 0;

    let html = "";

    if (loaded.length > 0) {
      html += `<div class="section-label">Loaded</div>`;
      html += `<div class="filaments">${loaded.map(f => this._renderFilament(f, "")).join("")}</div>`;
    }

    if (this._showStored && stored.length > 0) {
      html += `<div class="section-label">In Storage</div>`;
      html += `<div class="filaments">${stored.map(f => this._renderFilament(f, "stored")).join("")}</div>`;
    }

    if (this._showEmpty && empty.length > 0) {
      html += `<div class="section-label">Empty</div>`;
      html += `<div class="filaments">${empty.map(f => this._renderFilament(f, "empty-spool")).join("")}</div>`;
    }

    if (filaments.length === 0) {
      html = `<div class="no-filaments">No filament detected yet. Ensure the printer is on and trays are loaded.</div>`;
    }

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
          <span class="title">Filament Inventory</span>
          <span class="total">${filaments.length} spool${filaments.length !== 1 ? "s" : ""}</span>
        </div>
        ${html}
        ${footerHtml}
      </ha-card>
    `;
  }

  _findFilamentEntities() {
    const filaments = [];
    const states = this._hass.states;

    for (const entityId in states) {
      if (!entityId.startsWith("sensor.")) continue;
      const state = states[entityId];
      const attrs = state.attributes;
      if (!attrs || attrs.color_id === undefined || attrs.is_loaded === undefined) continue;

      const remaining = parseFloat(state.state) || 0;
      const startCap = attrs.start_capacity || 1000;
      const pct = startCap > 0 ? Math.round((remaining / startCap) * 100) : 0;
      const isLow = this._checkLow(attrs.spool_id);

      filaments.push({
        entityId,
        colorHex: attrs.color_id || "#cccccc",
        colorName: attrs.color || "Unknown",
        type: attrs.type || "PLA",
        isLoaded: attrs.is_loaded === true,
        loadedPosition: attrs.loaded_position,
        remaining: remaining,
        startCapacity: startCap,
        pct,
        isLow,
      });
    }

    const loaded = filaments.filter(f => f.isLoaded);
    loaded.sort((a, b) => (a.loadedPosition || 0) - (b.loadedPosition || 0));
    const rest = filaments.filter(f => !f.isLoaded);
    return [...loaded, ...rest];
  }

  _checkLow(spoolId) {
    if (!spoolId) return false;
    for (const eid in this._hass.states) {
      if (!eid.endsWith("_low")) continue;
      const s = this._hass.states[eid];
      if (s.state === "on" && s.attributes && s.attributes.spool_id === spoolId) return true;
    }
    return false;
  }

  _renderFilament(f, cssClass) {
    const barColor = f.isLow ? "var(--bft-low)" : f.colorHex;
    const lowClass = f.isLow ? " low" : "";
    const status = f.isLoaded ? `Tray ${f.loadedPosition}` : (f.remaining > 0 ? "Stored" : "Empty");

    return `
      <div class="filament ${cssClass}">
        <div class="color-dot" style="background: ${f.colorHex};"></div>
        <div class="filament-info">
          <div class="filament-top">
            <span class="filament-label">${f.colorName} &mdash; ${f.pct}%</span>
            <span class="filament-type">${f.type}</span>
          </div>
          <div class="bar-bg">
            <div class="bar-fill${lowClass}" style="width: ${f.pct}%; background: ${barColor};"></div>
          </div>
          <div class="filament-bottom">
            <span class="filament-status">${status}</span>
            <span class="filament-weight">${f.remaining}g / ${f.startCapacity}g</span>
          </div>
        </div>
      </div>`;
  }

  _formatWeight(g) {
    if (g >= 1000) return (g / 1000).toFixed(2) + "kg";
    return g.toFixed(1) + "g";
  }

  static getStubConfig() {
    return { entity_prefix: "filament_tracker", show_stored: true, show_empty: true, show_totals: true };
  }

  getCardSize() { return 5; }
}

customElements.define("bambu-filament-tracker-card", BambuFilamentTrackerCard);

console.info(
  "%c BAMBU-FILAMENT-TRACKER %c v" + CARD_VERSION + " ",
  "background:#4CAF50;color:white;font-weight:bold",
  "background:#333;color:white"
);
