const CARD_VERSION = 2;

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
  .spools {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .spool {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .spool.empty-spool {
    opacity: 0.45;
  }
  .spool.stored {
    opacity: 0.75;
  }
  .color-dot {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    flex-shrink: 0;
    border: 2px solid var(--bft-border);
  }
  .spool-info {
    flex: 1;
    min-width: 0;
  }
  .spool-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
  }
  .spool-label {
    font-size: 13px;
    font-weight: 500;
    color: var(--bft-text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 60%;
  }
  .spool-material {
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
  .spool-bottom {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 3px;
  }
  .spool-status {
    font-size: 11px;
    color: var(--bft-secondary);
    font-family: monospace;
  }
  .spool-weight {
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
  .no-spools {
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
    this._showEmpty = config.show_empty_spools !== false;
    this._showStored = config.show_stored_spools !== false;
    this._showTotals = config.show_totals !== false;
  }

  connectedCallback() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
  }

  _updateCard() {
    if (!this._hass || !this.shadowRoot) return;

    const spoolEntities = this._findSpoolEntities();
    const loaded = [];
    const stored = [];
    const empty = [];

    for (const s of spoolEntities) {
      if (s.status.startsWith("Loaded")) {
        loaded.push(s);
      } else if (s.status === "Stored") {
        stored.push(s);
      } else if (s.status === "Empty") {
        empty.push(s);
      }
    }

    const totalEntity = this._hass.states[`sensor.${this._prefix}_total_consumed`];
    const lastPrintEntity = this._hass.states[`sensor.${this._prefix}_last_print_usage`];
    const totalVal = totalEntity ? parseFloat(totalEntity.state) || 0 : 0;
    const lastPrintVal = lastPrintEntity ? parseFloat(lastPrintEntity.state) || 0 : 0;

    let html = "";

    if (loaded.length > 0) {
      html += `<div class="section-label">Loaded</div>`;
      html += `<div class="spools">${loaded.map(s => this._renderSpool(s, "")).join("")}</div>`;
    }

    if (this._showStored && stored.length > 0) {
      html += `<div class="section-label">In Storage</div>`;
      html += `<div class="spools">${stored.map(s => this._renderSpool(s, "stored")).join("")}</div>`;
    }

    if (this._showEmpty && empty.length > 0) {
      html += `<div class="section-label">Empty</div>`;
      html += `<div class="spools">${empty.map(s => this._renderSpool(s, "empty-spool")).join("")}</div>`;
    }

    if (spoolEntities.length === 0) {
      html = `<div class="no-spools">No spools registered. Use sync_from_tray service or register spools manually.</div>`;
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
          <span class="total">${spoolEntities.length} spool${spoolEntities.length !== 1 ? "s" : ""}</span>
        </div>
        ${html}
        ${footerHtml}
      </ha-card>
    `;
  }

  _findSpoolEntities() {
    const spools = [];
    const states = this._hass.states;

    for (const entityId in states) {
      if (!entityId.startsWith("sensor.") || !entityId.endsWith("_remaining")) continue;
      const state = states[entityId];
      if (!state.attributes || !state.attributes.spool_id) continue;
      if (!state.attributes.color_hex) continue;

      const spoolId = state.attributes.spool_id;
      const statusEntity = this._findStatusEntity(spoolId);

      spools.push({
        spoolId: spoolId,
        name: this._getDeviceName(entityId) || state.attributes.spool_id,
        colorHex: state.attributes.color_hex || "#cccccc",
        material: state.attributes.material || "PLA",
        brand: state.attributes.brand || "",
        remainingG: parseFloat(state.state) || 0,
        initialG: state.attributes.initial_weight_g || 1000,
        totalConsumedG: state.attributes.total_consumed_g || 0,
        status: statusEntity ? statusEntity.state : state.attributes.status || "Unknown",
        tray: state.attributes.tray,
        pct: this._calcPct(parseFloat(state.state) || 0, state.attributes.initial_weight_g || 1000),
        isLow: this._checkLow(spoolId),
      });
    }

    return spools;
  }

  _findStatusEntity(spoolId) {
    const entityId = `sensor.spool_${spoolId}_status`.replace(/-/g, "_");
    // HA normalizes entity IDs — search by spool_id attribute instead
    for (const eid in this._hass.states) {
      if (eid.endsWith("_status")) {
        const s = this._hass.states[eid];
        if (s.attributes && s.attributes.spool_id === spoolId) return s;
      }
    }
    return null;
  }

  _getDeviceName(entityId) {
    const state = this._hass.states[entityId];
    if (!state) return null;
    const friendly = state.attributes.friendly_name || "";
    return friendly.replace(" Remaining", "").trim() || null;
  }

  _calcPct(remaining, initial) {
    if (initial <= 0) return 0;
    return Math.round((remaining / initial) * 100);
  }

  _checkLow(spoolId) {
    for (const eid in this._hass.states) {
      if (eid.endsWith("_low")) {
        const s = this._hass.states[eid];
        if (s.attributes && s.attributes.spool_id === spoolId) return s.state === "on";
      }
    }
    return false;
  }

  _renderSpool(s, cssClass) {
    const barColor = s.isLow ? "var(--bft-low)" : s.colorHex;
    const lowClass = s.isLow ? " low" : "";
    const statusText = s.status;

    return `
      <div class="spool ${cssClass}">
        <div class="color-dot" style="background: ${s.colorHex};"></div>
        <div class="spool-info">
          <div class="spool-top">
            <span class="spool-label">${s.name} &mdash; ${s.pct}%</span>
            <span class="spool-material">${s.material}</span>
          </div>
          <div class="bar-bg">
            <div class="bar-fill${lowClass}" style="width: ${s.pct}%; background: ${barColor};"></div>
          </div>
          <div class="spool-bottom">
            <span class="spool-status">${statusText}</span>
            <span class="spool-weight">${s.remainingG}g / ${s.initialG}g</span>
          </div>
        </div>
      </div>`;
  }

  _formatWeight(g) {
    if (g >= 1000) {
      return (g / 1000).toFixed(2) + "kg";
    }
    return g.toFixed(1) + "g";
  }

  static getStubConfig() {
    return {
      entity_prefix: "filament_tracker",
      show_empty_spools: true,
      show_stored_spools: true,
      show_totals: true,
    };
  }

  getCardSize() {
    return 5;
  }
}

customElements.define("bambu-filament-tracker-card", BambuFilamentTrackerCard);

console.info(
  "%c BAMBU-FILAMENT-TRACKER %c v" + CARD_VERSION + " ",
  "background:#4CAF50;color:white;font-weight:bold",
  "background:#333;color:white"
);
