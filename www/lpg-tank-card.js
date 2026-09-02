/**
 * lpg-tank-card
 * Grafische Füllstandskarte für einen oberirdischen Flüssiggastank.
 *
 * https://github.com/tach2004/ha-fluessiggasverbrauch
 *
 * Besonderheit: Der Tank ist ein liegender Zylinder – die Flüssigkeitshöhe
 * verhält sich also NICHT linear zum Volumen (bei 50 % Volumen steht das Gas
 * genau in der Mitte, bei 85 % aber schon fast am Scheitel). Die Karte rechnet
 * das Volumen deshalb über die Kreissegmentfläche in eine Höhe um.
 */

const LPG_VERSION = "0.1.0";

const DEFAULTS = {
  name: "Flüssiggastank",
  entity_prozent: "sensor.gastank_inhalt_prozent",
  entity_liter: "sensor.gastank_inhalt",
  entity_energie: "sensor.gastank_restenergie",
  entity_wert: "sensor.gastank_restwert",
  entity_reichweite: "sensor.gastank_reichweite",
  entity_leer_am: "sensor.gastank_leer_am",
  entity_bestellen_bis: "sensor.gastank_bestellen_bis",
  entity_tagesverbrauch: "sensor.gastank_tagesverbrauch",
  entity_prognose: "sensor.gastank_prognose",
  entity_letzte_betankung: "input_datetime.gastank_letzte_betankung",
  entity_nennvolumen: "input_number.gastank_nennvolumen_liter",
  entity_max_prozent: "input_number.gastank_max_fuellgrad_prozent",
  entity_reserve: "input_number.gastank_reserve_liter",
  script_betankung: "script.gastank_betankung",
  script_korrektur: "script.gastank_fuellstand_korrigieren",
  warn_prozent: 25,   // % der nutzbaren Füllung -> gelb
  alarm_prozent: 12,  // % der nutzbaren Füllung -> rot
  betankung: true,    // Betankungsformular anbieten
  verlauf: true,      // Restverlauf der kommenden Monate zeichnen
  wellen: true,       // Wellenanimation
};

/* ------------------------------------------------------------------ Mathe */

/**
 * Füllhöhe eines liegenden Zylinders als Anteil des Durchmessers.
 * @param {number} f Volumenanteil 0..1
 * @returns {number} Höhenanteil 0..1
 */
function fuellhoehe(f) {
  if (!isFinite(f) || f <= 0) return 0;
  if (f >= 1) return 1;
  const R = 0.5;
  const flaeche = (h) =>
    (R * R * Math.acos((R - h) / R) - (R - h) * Math.sqrt(Math.max(0, 2 * R * h - h * h))) /
    (Math.PI * R * R);
  let lo = 0, hi = 1;
  for (let i = 0; i < 40; i++) {
    const mid = (lo + hi) / 2;
    if (flaeche(mid) < f) lo = mid; else hi = mid;
  }
  return (lo + hi) / 2;
}

/* --------------------------------------------------------------- Helfer */

const NICHTS = ["unknown", "unavailable", "none", "None", "", null, undefined];

function istWert(s) {
  return s && !NICHTS.includes(s.state);
}

function zahl(hass, entity, fallback = null) {
  const s = hass && hass.states[entity];
  if (!istWert(s)) return fallback;
  const v = parseFloat(s.state);
  return isNaN(v) ? fallback : v;
}

/* ----------------------------------------------------------------- Karte */

class LpgTankCard extends HTMLElement {
  static getStubConfig() {
    return { type: "custom:lpg-tank-card" };
  }

  setConfig(config) {
    this._config = Object.assign({}, DEFAULTS, config || {});
    this._formOffen = false;
    this._modus = "liefermenge";
    if (this.shadowRoot) this._root = null;
    this.innerHTML = "";
  }

  getCardSize() {
    return this._config && this._config.betankung ? 7 : 6;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._root) this._aufbauen();
    const sig = this._signatur();
    if (sig === this._signaturAlt) return;
    this._signaturAlt = sig;
    this._aktualisieren();
  }

  /** Fingerabdruck aller genutzten Zustände – spart Neuzeichnen bei fremden Events. */
  _signatur() {
    const c = this._config;
    return Object.keys(c)
      .filter((k) => k.startsWith("entity_"))
      .map((k) => {
        const s = this._hass.states[c[k]];
        return s ? s.state : "-";
      })
      .join("|") + "|" + ((this._hass.states[c.entity_prognose] || {}).last_updated || "");
  }

  /* ------------------------------------------------------------- Aufbau */

  _aufbauen() {
    const root = this.attachShadow ? (this.shadowRoot || this.attachShadow({ mode: "open" })) : this;
    root.innerHTML = `
      <style>
        :host {
          display: block;
          --lpg-gut: #2f7fd6;
          --lpg-warn: #f0a202;
          --lpg-alarm: #e23c34;
        }
        ha-card {
          padding: 16px;
          display: flex;
          flex-direction: column;
          gap: 12px;
          --lpg-gut: #2f7fd6;
          --lpg-warn: #f0a202;
          --lpg-alarm: #e23c34;
        }
        .kopf {
          display: flex; align-items: center; gap: 8px;
        }
        .titel {
          font-size: 1.15rem; font-weight: 500; flex: 1;
          color: var(--primary-text-color);
        }
        .kopf-knopf {
          background: none; border: none; cursor: pointer;
          color: var(--secondary-text-color);
          border-radius: 50%; width: 36px; height: 36px;
          display: grid; place-items: center;
        }
        .kopf-knopf:hover { background: var(--secondary-background-color); color: var(--primary-text-color); }
        .kopf-knopf[aria-pressed="true"] { color: var(--primary-color); }

        svg { width: 100%; height: auto; display: block; overflow: visible; }
        .huelle { fill: var(--card-background-color); stroke: var(--divider-color); stroke-width: 2.5; }
        .fluessig { fill: var(--lpg-farbe, var(--lpg-gut)); transition: fill .4s ease; }
        .fluessig-hell { fill: var(--lpg-farbe, var(--lpg-gut)); opacity: .45; }
        .liquid-g { transition: transform .8s cubic-bezier(.4,0,.2,1); }
        .metall { fill: var(--divider-color); }
        .marke { stroke: var(--secondary-text-color); stroke-width: 1.5; stroke-dasharray: 5 4; opacity: .65; fill: none; }
        .marke-alarm { stroke: var(--lpg-alarm); stroke-width: 1.5; stroke-dasharray: 5 4; opacity: .8; fill: none; }
        .skala { fill: var(--secondary-text-color); font-size: 11px; }
        .gross {
          font-size: 34px; font-weight: 600; text-anchor: middle;
          fill: var(--primary-text-color);
          stroke: var(--card-background-color); stroke-width: 7px;
          paint-order: stroke fill;
        }
        .klein {
          font-size: 13px; text-anchor: middle; fill: var(--secondary-text-color);
          stroke: var(--card-background-color); stroke-width: 5px;
          paint-order: stroke fill;
        }

        @keyframes lpg-welle { from { transform: translateX(0); } to { transform: translateX(-120px); } }
        .welle-1 { animation: lpg-welle 7s linear infinite; }
        .welle-2 { animation: lpg-welle 11s linear infinite reverse; }
        @media (prefers-reduced-motion: reduce) { .welle-1, .welle-2 { animation: none; } }

        .unterschrift {
          text-align: center; font-size: .95rem; color: var(--secondary-text-color);
          margin-top: -4px;
        }
        #verlauf { margin: 0 -4px; }
        #verlauf[hidden] { display: none; }
        .v-flaeche { fill: var(--lpg-farbe, var(--lpg-gut)); opacity: .18; }
        .v-linie { fill: none; stroke: var(--lpg-farbe, var(--lpg-gut)); stroke-width: 2.5;
                   stroke-linejoin: round; stroke-linecap: round; }
        .v-reserve { stroke: var(--lpg-alarm); stroke-width: 1.2; stroke-dasharray: 4 4; opacity: .7; }
        .v-achse { stroke: var(--divider-color); stroke-width: 1; }
        .v-text { fill: var(--secondary-text-color); font-size: 10px; }
        .v-punkt { fill: var(--lpg-alarm); }

        .kacheln {
          display: grid; grid-template-columns: repeat(auto-fit, minmax(142px, 1fr)); gap: 8px;
        }
        .kachel {
          background: var(--secondary-background-color);
          border-radius: 12px; padding: 10px 12px; cursor: pointer;
          display: flex; flex-direction: column; gap: 2px;
          border: none; text-align: left; font-family: inherit;
        }
        .kachel:hover { background: var(--divider-color); }
        .kachel .k-label { font-size: .75rem; color: var(--secondary-text-color); }
        .kachel .k-wert { font-size: 1.05rem; font-weight: 500; color: var(--primary-text-color); }
        .kachel .k-zusatz { font-size: .72rem; color: var(--secondary-text-color); }

        .fuss {
          display: flex; flex-wrap: wrap; gap: 4px 16px;
          font-size: .8rem; color: var(--secondary-text-color);
        }

        .formular {
          border-top: 1px solid var(--divider-color); padding-top: 12px;
          display: flex; flex-direction: column; gap: 10px;
        }
        .formular[hidden] { display: none; }
        .schalter { display: flex; gap: 8px; }
        .schalter button {
          flex: 1; padding: 8px; border-radius: 10px; cursor: pointer;
          border: 1px solid var(--divider-color);
          background: var(--card-background-color); color: var(--primary-text-color);
          font-family: inherit; font-size: .85rem;
        }
        .schalter button[aria-pressed="true"] {
          background: var(--primary-color); color: var(--text-primary-color, #fff);
          border-color: var(--primary-color);
        }
        .feld { display: flex; flex-direction: column; gap: 4px; }
        .feld label { font-size: .78rem; color: var(--secondary-text-color); }
        .feld input {
          padding: 8px 10px; border-radius: 8px; font-size: .95rem; font-family: inherit;
          border: 1px solid var(--divider-color);
          background: var(--card-background-color); color: var(--primary-text-color);
        }
        .hinweis { font-size: .72rem; color: var(--secondary-text-color); }
        .aktionen { display: flex; gap: 8px; justify-content: flex-end; }
        .aktionen button {
          padding: 8px 16px; border-radius: 10px; cursor: pointer;
          font-family: inherit; font-size: .9rem; border: 1px solid var(--divider-color);
          background: var(--card-background-color); color: var(--primary-text-color);
        }
        .aktionen button.primaer {
          background: var(--primary-color); color: var(--text-primary-color, #fff);
          border-color: var(--primary-color);
        }
        .fehler {
          background: var(--secondary-background-color); border-radius: 8px;
          padding: 12px; font-size: .85rem; color: var(--primary-text-color);
        }
        .fehler code { font-size: .78rem; word-break: break-all; }
      </style>

      <ha-card>
        <div class="kopf">
          <ha-icon icon="mdi:propane-tank"></ha-icon>
          <div class="titel"></div>
          <button class="kopf-knopf" id="knopf-form" title="Betankung eintragen" aria-pressed="false">
            <ha-icon icon="mdi:gas-station"></ha-icon>
          </button>
        </div>

        <div id="fehler" class="fehler" hidden></div>

        <svg viewBox="0 0 420 215" role="img" id="grafik">
          <defs>
            <clipPath id="lpg-clip">
              <path d="M 86,48 H 334 A 26,60 0 0 1 334,168 H 86 A 26,60 0 0 0 86,48 Z"/>
            </clipPath>
          </defs>

          <!-- Sattel / Füße -->
          <rect class="metall" x="112" y="166" width="26" height="18" rx="3"/>
          <rect class="metall" x="282" y="166" width="26" height="18" rx="3"/>
          <rect class="metall" x="96"  y="182" width="58" height="6" rx="3"/>
          <rect class="metall" x="266" y="182" width="58" height="6" rx="3"/>

          <!-- Domhaube -->
          <rect class="huelle" x="182" y="30" width="56" height="22" rx="7"/>
          <rect class="metall" x="204" y="22" width="12" height="10" rx="2"/>

          <!-- Flüssigkeit -->
          <g clip-path="url(#lpg-clip)">
            <g id="liquid" class="liquid-g" transform="translate(0,168)">
              <rect class="fluessig" x="40" y="0" width="360" height="320"/>
              <g class="welle-1"><path id="w1" class="fluessig-hell" d=""/></g>
              <g class="welle-2"><path id="w2" class="fluessig" d=""/></g>
            </g>
          </g>

          <!-- Tankkontur -->
          <path class="huelle" style="fill:none" d="M 86,48 H 334 A 26,60 0 0 1 334,168 H 86 A 26,60 0 0 0 86,48 Z"/>

          <!-- Markierungen -->
          <line id="marke-max" class="marke" x1="70" y1="0" x2="350" y2="0"/>
          <text id="marke-max-text" class="skala" x="356" y="0" dominant-baseline="middle">85 %</text>
          <line id="marke-reserve" class="marke-alarm" x1="70" y1="0" x2="350" y2="0"/>
          <text id="marke-reserve-text" class="skala" x="356" y="0" dominant-baseline="middle">Reserve</text>

          <text id="t-prozent" class="gross" x="210" y="103">–</text>
        </svg>

        <div class="unterschrift" id="t-liter">–</div>
        <svg id="verlauf" viewBox="0 0 420 96" role="img" aria-label="Restverlauf"></svg>
        <div class="kacheln" id="kacheln"></div>
        <div class="fuss" id="fuss"></div>

        <div class="formular" id="formular" hidden>
          <div class="schalter">
            <button id="m-liefermenge" aria-pressed="true">Getankte Menge</button>
            <button id="m-tankuhr" aria-pressed="false">Tankuhr ablesen</button>
          </div>

          <div id="block-liefermenge">
            <div class="feld">
              <label for="f-liter">Liefermenge (Liter laut Lieferschein)</label>
              <input id="f-liter" type="number" min="0" step="1" inputmode="decimal" placeholder="z. B. 2500">
            </div>
            <div class="feld" style="margin-top:8px">
              <label for="f-vorher">Tankuhr direkt vor dem Tanken (%, optional)</label>
              <input id="f-vorher" type="number" min="0" max="100" step="0.5" inputmode="decimal" placeholder="z. B. 22">
            </div>
            <div class="hinweis">
              Wenn du den Wert vor der Betankung angibst, kalibriert sich die Umrechnung
              m³ → Liter automatisch an der Realität.
            </div>
          </div>

          <div id="block-tankuhr" hidden>
            <div class="feld">
              <label for="f-prozent">Aktueller Wert der Tankuhr (%)</label>
              <input id="f-prozent" type="number" min="0" max="100" step="0.5" inputmode="decimal" placeholder="z. B. 62">
            </div>
            <div class="hinweis">
              Setzt den Füllstand direkt auf den abgelesenen Wert und startet die
              Verbrauchszählung neu – ideal für die Ersteinrichtung.
            </div>
          </div>

          <div class="feld" id="block-datum">
            <label for="f-datum">Datum</label>
            <input id="f-datum" type="date">
          </div>

          <div class="aktionen">
            <button id="f-abbrechen">Abbrechen</button>
            <button id="f-speichern" class="primaer">Speichern</button>
          </div>
        </div>
      </ha-card>
    `;

    this._root = root;
    this._el = {};
    ["titel", "fehler", "grafik", "liquid", "w1", "w2", "t-prozent", "t-liter", "verlauf",
     "marke-max", "marke-max-text", "marke-reserve", "marke-reserve-text",
     "kacheln", "fuss", "formular", "knopf-form",
     "m-liefermenge", "m-tankuhr", "block-liefermenge", "block-tankuhr",
     "f-liter", "f-vorher", "f-prozent", "f-datum", "f-abbrechen", "f-speichern"]
      .forEach((id) => {
        this._el[id] = root.getElementById ? root.getElementById(id) : root.querySelector("#" + id);
      });
    this._el.titel = root.querySelector(".titel");

    this._wellenZeichnen();
    this._ereignisse();
  }

  _wellenZeichnen() {
    const welle = (amp, phase, schritt) => {
      let d = `M -200,0`;
      for (let x = -200; x <= 620; x += schritt) {
        const y = amp * Math.sin((x / 120) * 2 * Math.PI + phase);
        d += ` L ${x},${y.toFixed(2)}`;
      }
      return d + " L 620,320 L -200,320 Z";
    };
    if (this._el.w1) this._el.w1.setAttribute("d", welle(4.5, 0, 6));
    if (this._el.w2) this._el.w2.setAttribute("d", welle(3.0, Math.PI / 2, 6));
    if (!this._config.wellen) {
      [this._el.w1, this._el.w2].forEach((p) => p && p.parentElement.remove());
    }
  }

  _ereignisse() {
    const e = this._el;
    e["knopf-form"].addEventListener("click", () => {
      this._formOffen = !this._formOffen;
      e.formular.hidden = !this._formOffen;
      e["knopf-form"].setAttribute("aria-pressed", String(this._formOffen));
      if (this._formOffen && !e["f-datum"].value) {
        e["f-datum"].value = new Date().toISOString().slice(0, 10);
      }
    });
    e["f-abbrechen"].addEventListener("click", () => e["knopf-form"].click());

    const modus = (m) => {
      this._modus = m;
      e["m-liefermenge"].setAttribute("aria-pressed", String(m === "liefermenge"));
      e["m-tankuhr"].setAttribute("aria-pressed", String(m === "tankuhr"));
      e["block-liefermenge"].hidden = m !== "liefermenge";
      e["block-tankuhr"].hidden = m !== "tankuhr";
    };
    e["m-liefermenge"].addEventListener("click", () => modus("liefermenge"));
    e["m-tankuhr"].addEventListener("click", () => modus("tankuhr"));

    e["f-speichern"].addEventListener("click", () => this._speichern());
  }

  /* ------------------------------------------------------------ Aktionen */

  _dienst(entityId) {
    const [domain, obj] = entityId.split(".");
    return { domain, obj };
  }

  _speichern() {
    const e = this._el;
    const c = this._config;
    if (this._modus === "tankuhr") {
      const p = parseFloat(e["f-prozent"].value);
      if (isNaN(p)) return this._blinken(e["f-prozent"]);
      const s = this._dienst(c.script_korrektur);
      this._hass.callService(s.domain, s.obj, { fuellstand_prozent: p });
    } else {
      const liter = parseFloat(e["f-liter"].value);
      const vorher = parseFloat(e["f-vorher"].value);
      if (isNaN(liter) && isNaN(vorher)) return this._blinken(e["f-liter"]);
      const data = {};
      if (!isNaN(liter)) data.getankte_liter = liter;
      if (!isNaN(vorher)) data.fuellstand_vorher_prozent = vorher;
      if (e["f-datum"].value) data.datum = e["f-datum"].value;
      const s = this._dienst(c.script_betankung);
      this._hass.callService(s.domain, s.obj, data);
    }
    e["f-liter"].value = "";
    e["f-vorher"].value = "";
    e["f-prozent"].value = "";
    e["knopf-form"].click();
  }

  _blinken(el) {
    el.style.borderColor = "var(--lpg-alarm, #e23c34)";
    setTimeout(() => { el.style.borderColor = ""; }, 1200);
    el.focus();
  }

  _mehrInfo(entityId) {
    this.dispatchEvent(new CustomEvent("hass-more-info", {
      detail: { entityId }, bubbles: true, composed: true,
    }));
  }

  /* --------------------------------------------------------- Darstellung */

  _fmt(v, nk = 0, einheit = "") {
    if (v === null || v === undefined || isNaN(v)) return "–";
    const lang = (this._hass && this._hass.locale && this._hass.locale.language) || "de";
    const s = new Intl.NumberFormat(lang, {
      minimumFractionDigits: nk, maximumFractionDigits: nk,
    }).format(v);
    return einheit ? `${s} ${einheit}` : s;
  }

  _datum(entityId) {
    const s = this._hass.states[entityId];
    if (!istWert(s)) return null;
    return this._parse(s.state);
  }

  /** "2026-09-02" ohne Uhrzeit wuerde als UTC-Mitternacht gelesen und in
   *  westlichen Zeitzonen einen Tag zu frueh angezeigt. */
  _parse(text) {
    const roh = /^\d{4}-\d{2}-\d{2}$/.test(text) ? `${text}T12:00:00` : text;
    const d = new Date(roh);
    return isNaN(d.getTime()) ? null : d;
  }

  _datumText(d) {
    if (!d) return "–";
    const lang = (this._hass && this._hass.locale && this._hass.locale.language) || "de";
    return d.toLocaleDateString(lang, { day: "2-digit", month: "2-digit", year: "numeric" });
  }

  _aktualisieren() {
    const c = this._config;
    const h = this._hass;
    const e = this._el;
    if (!h || !e) return;

    e.titel.textContent = c.name;

    // Pflichtentität prüfen
    const fehlend = [c.entity_liter, c.entity_prozent].filter((id) => !h.states[id]);
    if (fehlend.length) {
      e.fehler.hidden = false;
      e.fehler.innerHTML =
        "Entität nicht gefunden: " + fehlend.map((f) => `<code>${f}</code>`).join(", ") +
        "<br>Package eingebunden und Home Assistant neu gestartet?";
      e.grafik.style.opacity = ".35";
      return;
    }
    e.fehler.hidden = true;
    e.grafik.style.opacity = "1";

    const liter = zahl(h, c.entity_liter, 0);
    const nenn = zahl(h, c.entity_nennvolumen, 4850);
    const maxP = zahl(h, c.entity_max_prozent, 85);
    const reserve = zahl(h, c.entity_reserve, 0);
    const prozent = zahl(h, c.entity_prozent, (liter / Math.max(nenn, 1)) * 100);
    const nutzbar = nenn * (maxP / 100);
    const nutzProzent = (liter / Math.max(nutzbar, 1)) * 100;

    // Farbe nach Restfüllung
    const farbe =
      nutzProzent <= c.alarm_prozent ? "var(--lpg-alarm)"
      : nutzProzent <= c.warn_prozent ? "var(--lpg-warn)"
      : "var(--lpg-gut)";
    this.style.setProperty("--lpg-farbe", farbe);

    // Geometrie: Tankinnenraum y = 48 (oben) .. 168 (unten)
    const yOben = 48, yUnten = 168, hoehe = yUnten - yOben;
    const yFuer = (anteil) => yUnten - fuellhoehe(Math.max(0, Math.min(1, anteil))) * hoehe;

    e.liquid.setAttribute("transform", `translate(0,${yFuer(prozent / 100).toFixed(2)})`);

    const yMax = yFuer(maxP / 100);
    e["marke-max"].setAttribute("y1", yMax); e["marke-max"].setAttribute("y2", yMax);
    e["marke-max-text"].setAttribute("y", yMax);
    e["marke-max-text"].textContent = `${this._fmt(maxP, 0)} %`;

    const zeigeReserve = reserve > 0 && reserve < nutzbar;
    const yRes = yFuer(reserve / Math.max(nenn, 1));
    ["marke-reserve", "marke-reserve-text"].forEach((k) => {
      e[k].style.display = zeigeReserve ? "" : "none";
    });
    if (zeigeReserve) {
      e["marke-reserve"].setAttribute("y1", yRes); e["marke-reserve"].setAttribute("y2", yRes);
      e["marke-reserve-text"].setAttribute("y", yRes);
    }

    e["t-prozent"].textContent = `${this._fmt(prozent, 1)} %`;
    e["t-liter"].textContent =
      `${this._fmt(liter, 0)} von ${this._fmt(nutzbar, 0)} L` +
      (zahl(h, c.entity_energie, null) !== null
        ? ` · ${this._fmt(zahl(h, c.entity_energie), 0)} kWh` : "");

    this._verlaufZeichnen(reserve, nenn);

    // ------------------------------------------------------------ Kacheln
    const leerAm = this._datum(c.entity_leer_am);
    const bestellen = this._datum(c.entity_bestellen_bis);
    const reichweite = zahl(h, c.entity_reichweite, null);
    const energie = zahl(h, c.entity_energie, null);
    const wert = zahl(h, c.entity_wert, null);
    const proTag = zahl(h, c.entity_tagesverbrauch, null);

    const kacheln = [
      { label: "Restenergie", wert: this._fmt(energie, 0, "kWh"),
        zusatz: wert !== null ? this._fmt(wert, 0, "EUR") : "", entity: c.entity_energie },
      { label: "Ø Verbrauch", wert: this._fmt(proTag, 1, "L/d"),
        zusatz: proTag !== null ? this._fmt(proTag * 30, 0, "L/Monat") : "", entity: c.entity_tagesverbrauch },
      { label: "Reichweite", wert: reichweite !== null ? this._fmt(reichweite, 0, "Tage") : "–",
        zusatz: reichweite !== null ? `≈ ${this._fmt(reichweite / 30.44, 1)} Monate` : "",
        entity: c.entity_reichweite },
      { label: "Voraussichtlich leer", wert: this._datumText(leerAm),
        zusatz: leerAm ? this._wochentag(leerAm) : "", entity: c.entity_leer_am },
    ];

    e.kacheln.innerHTML = kacheln.map((k, i) => `
      <button class="kachel" data-i="${i}">
        <span class="k-label">${k.label}</span>
        <span class="k-wert">${k.wert}</span>
        <span class="k-zusatz">${k.zusatz || "&nbsp;"}</span>
      </button>`).join("");
    e.kacheln.querySelectorAll(".kachel").forEach((el) => {
      el.addEventListener("click", () => this._mehrInfo(kacheln[parseInt(el.dataset.i, 10)].entity));
    });

    // -------------------------------------------------------------- Fuß
    const letzte = h.states[c.entity_letzte_betankung];
    const letzteText = istWert(letzte) ? this._datumText(this._parse(letzte.state)) : "–";
    const teile = [`Letzte Betankung: ${letzteText}`];
    if (bestellen) {
      const tage = Math.round((bestellen - new Date()) / 86400000);
      teile.push(tage <= 0
        ? `Bestellung fällig (seit ${Math.abs(tage)} Tagen)`
        : `Bestellen bis ${this._datumText(bestellen)}`);
    }
    e.fuss.textContent = teile.join(" · ");
  }

  /**
   * Restverlauf der kommenden Monate aus dem Attribut "monate" der
   * Prognose-Entität. Zeigt auf einen Blick, wie weit die Füllung trägt
   * und wo sie durch die Reserve läuft.
   */
  _verlaufZeichnen(reserve, nenn) {
    const svg = this._el.verlauf;
    if (!svg) return;
    const c = this._config;
    const prog = this._hass.states[c.entity_prognose];
    const monate = (prog && prog.attributes && prog.attributes.monate) || [];
    if (!c.verlauf || monate.length < 2) { svg.hidden = true; return; }
    svg.hidden = false;

    const punkte = monate.slice(0, 36);
    const B = 420, H = 96, l = 6, r = 6, o = 8, u = 20;
    const maxRest = Math.max(...punkte.map((m) => m.rest), nenn * 0.1);
    const x = (i) => l + (i / (punkte.length - 1)) * (B - l - r);
    const y = (v) => o + (1 - v / maxRest) * (H - o - u);

    const linie = punkte.map((m, i) => `${i ? "L" : "M"} ${x(i).toFixed(1)},${y(m.rest).toFixed(1)}`).join(" ");
    const flaeche = `${linie} L ${x(punkte.length - 1).toFixed(1)},${y(0).toFixed(1)} L ${x(0).toFixed(1)},${y(0).toFixed(1)} Z`;

    // Beschriftung: jeder Jahreswechsel plus Anfang und Ende
    const lang = (this._hass.locale && this._hass.locale.language) || "de";
    const schritt = Math.max(1, Math.ceil(punkte.length / 7));
    let letztesJahr = null;
    const letzter = punkte.length - 1;
    const vorletzterTick = Math.floor(letzter / schritt) * schritt;
    const labels = punkte
      .map((m, i) => ({ m, i }))
      // letzten Monat nur beschriften, wenn er nicht am vorherigen Tick klebt
      .filter(({ i }) => i % schritt === 0 || (i === letzter && x(letzter) - x(vorletzterTick) > 46))
      .map(({ m, i }) => {
        const [j, mo] = m.monat.split("-");
        const d = new Date(Number(j), Number(mo) - 1, 1);
        const text = d.toLocaleDateString(lang, { month: "short" }) +
          (j !== letztesJahr ? ` ${j.slice(2)}` : "");
        letztesJahr = j;
        return `<text class="v-text" x="${x(i).toFixed(1)}" y="${H - 6}" text-anchor="${
          i === 0 ? "start" : i >= letzter - 1 ? "end" : "middle"}">${text}</text>`;
      })
      .join("");

    const reserveLinie = reserve > 0 && reserve < maxRest
      ? `<line class="v-reserve" x1="${l}" y1="${y(reserve).toFixed(1)}" x2="${B - r}" y2="${y(reserve).toFixed(1)}"/>
         <text class="v-text" x="${l}" y="${(y(reserve) - 4).toFixed(1)}">Reserve</text>`
      : "";

    const leer = punkte[punkte.length - 1].rest <= 0
      ? `<circle class="v-punkt" cx="${x(punkte.length - 1).toFixed(1)}" cy="${y(0).toFixed(1)}" r="3.5"/>`
      : "";

    svg.innerHTML = `
      <line class="v-achse" x1="${l}" y1="${y(0).toFixed(1)}" x2="${B - r}" y2="${y(0).toFixed(1)}"/>
      <path class="v-flaeche" d="${flaeche}"/>
      <path class="v-linie" d="${linie}"/>
      ${reserveLinie}${leer}${labels}`;
  }

  _wochentag(d) {
    const lang = (this._hass && this._hass.locale && this._hass.locale.language) || "de";
    const tage = Math.round((d - new Date()) / 86400000);
    return `${d.toLocaleDateString(lang, { weekday: "long" })} · in ${tage} Tagen`;
  }
}

customElements.define("lpg-tank-card", LpgTankCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "lpg-tank-card",
  name: "Flüssiggastank",
  preview: false,
  description: "Grafischer Füllstand eines liegenden Flüssiggastanks inkl. Leer-Prognose und Betankungseingabe.",
  documentationURL: "https://github.com/tach2004/ha-fluessiggasverbrauch",
});

console.info(
  `%c LPG-TANK-CARD %c ${LPG_VERSION} `,
  "color:#fff;background:#2f7fd6;font-weight:700",
  "color:#2f7fd6;background:#eee"
);
