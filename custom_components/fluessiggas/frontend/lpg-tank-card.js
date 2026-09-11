/**
 * lpg-tank-card
 * Grafische Füllstandskarte für einen oberirdischen Flüssiggastank.
 *
 * Gehört zur Integration "fluessiggas" und wird von ihr automatisch
 * eingebunden – ein Eintrag unter Dashboards → Ressourcen ist nicht nötig.
 * https://github.com/tach2004/ha-fluessiggasverbrauch
 *
 * Ohne Konfiguration findet die Karte ihren Tank selbst: Die Integration
 * markiert jede Entität mit den Attributen `tank_id` und `kennung`, deshalb
 * sind weder Entity-IDs noch eine bestimmte Sprache nötig.
 *
 *   type: custom:lpg-tank-card          # das genügt bei einem Tank
 *   tank: 01JABC…                       # tank_id oder Name, bei mehreren Tanks
 *   entities: { inhalt: sensor.xyz }    # optionale Handkorrektur
 *
 * Die Farbschwellen kommen aus der Integration (Reserve und Warnschwelle),
 * damit sie nicht an zwei Stellen gepflegt werden müssen.
 *
 * Besonderheit der Grafik: Der Tank ist ein liegender Zylinder – die
 * Flüssigkeitshöhe verhält sich also NICHT linear zum Volumen (bei 50 %
 * steht das Gas genau in der Mitte, bei 85 % schon fast am Scheitel).
 * Die Karte rechnet das Volumen über die Kreissegmentfläche in eine Höhe um.
 */

// Die Version kommt aus der URL, mit der die Integration die Karte einbindet
// (…/lpg-tank-card.js?v=1.3.0). So steht sie nur in der manifest.json und
// muss hier nicht gepflegt werden. Setzt voraus, dass die Datei als Modul
// geladen wird - genau so bindet Home Assistant sie ein.
const LPG_VERSION = new URL(import.meta.url).searchParams.get("v") || "unbekannt";

/** Kennungen, die die Integration an ihren Entitäten hinterlässt. */
const KENNUNGEN = [
  "inhalt", "inhalt_prozent", "inhalt_nutzbar", "restenergie", "restwert",
  "gaspreis", "umrechnungsfaktor", "verbrauch_seit_betankung", "tagesverbrauch",
  "jahr_liter", "jahr_kubik", "jahr_energie", "jahresverbrauch",
  "reichweite", "leer_am", "reserve_am", "bestellen_bis", "letzte_betankung",
];

/** Reiter des Eingabeformulars. */
const MODI = ["liefermenge", "tankuhr", "nachtragen", "verlauf"];

const DEFAULTS = {
  name: null,         // null = Name des Tanks aus Home Assistant
  tank: null,         // tank_id oder Namensteil, nur bei mehreren Tanks nötig
  entities: {},       // manuelle Zuordnung, z. B. { inhalt: "sensor.xyz" }
  betankung: true,    // Betankungsformular anbieten
  verlauf: true,      // Restverlauf der kommenden Monate zeichnen
  preisverlauf: true, // Preisentwicklung der eingetragenen Lieferungen
  jahr: true,         // Verbrauch des laufenden Kalenderjahres in drei Einheiten
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

function zahl(zustand, fallback = null) {
  if (!istWert(zustand)) return fallback;
  const v = parseFloat(zustand.state);
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
    this._signaturAlt = null;
  }

  /**
   * Sucht die Entitäten des Tanks anhand der Attribute, die die Integration
   * setzt. Gibt zusätzlich zurück, welche Tanks überhaupt gefunden wurden,
   * damit die Karte bei mehreren Tanks um eine Angabe bitten kann.
   */
  _finden() {
    const treffer = {};
    const tanks = new Set();
    const wunsch = this._config.tank;
    for (const [id, zustand] of Object.entries(this._hass.states)) {
      const a = zustand.attributes || {};
      if (!a.tank_id || !a.kennung) continue;
      tanks.add(a.tank_id);
      if (wunsch && a.tank_id !== wunsch && !id.includes(wunsch) &&
          !(a.friendly_name || "").includes(wunsch)) continue;
      if (!treffer[a.kennung]) treffer[a.kennung] = id;
    }
    return { treffer: Object.assign(treffer, this._config.entities || {}), tanks };
  }

  _zustand(kennung) {
    const id = this._ent && this._ent[kennung];
    return id ? this._hass.states[id] : undefined;
  }

  getCardSize() {
    return this._config && this._config.betankung ? 7 : 6;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._root) this._aufbauen();
    const { treffer, tanks } = this._finden();
    this._ent = treffer;
    this._tanks = tanks;
    const sig = this._signatur();
    if (sig === this._signaturAlt) return;
    this._signaturAlt = sig;
    this._aktualisieren();
  }

  /** Fingerabdruck der genutzten Zustände – spart Neuzeichnen bei fremden Events. */
  _signatur() {
    return KENNUNGEN.map((k) => {
      const z = this._zustand(k);
      return z ? `${z.state}@${z.last_updated}` : "-";
    }).join("|");
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

        .abschnitt {
          display: flex; justify-content: space-between; align-items: baseline;
          /* Umbrechen statt kollidieren: In einer schmalen Spalte klebten
             die beiden Beschriftungen sonst aneinander. Bewusst ohne
             Spaltenabstand - space-between verteilt den Platz ohnehin, und
             ein Mindestabstand würde die einzeilige Darstellung zu früh
             sprengen. */
          flex-wrap: wrap; row-gap: 2px;
          font-size: .78rem; color: var(--secondary-text-color);
          border-top: 1px solid var(--divider-color); padding-top: 10px;
        }
        #preisblock[hidden] { display: none; }
        #preise { margin: 2px -4px 0; }
        .p-linie { fill: none; stroke: var(--primary-color); stroke-width: 2.5;
                   stroke-linejoin: round; stroke-linecap: round; }
        .p-punkt { fill: var(--primary-color); }
        .p-punkt-letzt { fill: var(--primary-color); stroke: var(--card-background-color);
                         stroke-width: 2.5; }
        .p-schnitt { stroke: var(--secondary-text-color); stroke-width: 1;
                     stroke-dasharray: 4 4; opacity: .5; }
        .p-text { fill: var(--secondary-text-color); font-size: 10px; }
        .p-kreuz { stroke: var(--primary-text-color); stroke-width: 1; opacity: .45; }
        .p-treffer { fill: var(--primary-color); stroke: var(--card-background-color); stroke-width: 2; }
        .p-box { fill: var(--card-background-color); stroke: var(--divider-color); stroke-width: 1; }
        .p-boxtext { fill: var(--primary-text-color); font-size: 11px; }
        .p-wert { fill: var(--primary-text-color); font-size: 11px; font-weight: 500; }

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

        /* Die drei Jahreswerte sind dieselbe Menge in drei Einheiten. Sie
           stehen deshalb in einer eigenen, schmaleren Reihe statt als drei
           volle Kacheln - sonst erschlagen sie die Karte. */
        .jahr {
          display: grid; grid-template-columns: repeat(auto-fit, minmax(84px, 1fr));
          gap: 8px; margin-top: 8px;
        }
        .jahr .kachel { padding: 8px; }
        /* Kein nowrap: In einer sehr schmalen Spalte soll "8.715 kWh"
           umbrechen und nicht abgeschnitten werden. */
        .jahr .kachel .k-wert { font-size: .9rem; }

        .fuss {
          display: flex; flex-wrap: wrap; gap: 4px 16px;
          font-size: .8rem; color: var(--secondary-text-color);
        }

        .formular {
          border-top: 1px solid var(--divider-color); padding-top: 12px;
          display: flex; flex-direction: column; gap: 10px;
        }
        /* Ein Klassen-Selektor mit display schlägt die Browser-Vorgabe
           [hidden] { display: none }. Ohne diese Zeile bleibt z. B. das
           Datumsfeld (.feld) sichtbar, obwohl es hidden gesetzt ist. */
        [hidden] { display: none !important; }
        .schalter { display: flex; gap: 6px; flex-wrap: wrap; }
        .schalter button {
          flex: 1 1 84px; padding: 8px 4px; border-radius: 10px; cursor: pointer;
          border: 1px solid var(--divider-color);
          background: var(--card-background-color); color: var(--primary-text-color);
          font-family: inherit; font-size: .82rem;
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

        .ruecknahme {
          width: 100%; padding: 9px 12px; border-radius: 10px; cursor: pointer;
          font-family: inherit; font-size: .85rem; text-align: left;
          border: 1px solid var(--lpg-warn, #e8a33d);
          background: var(--card-background-color); color: var(--primary-text-color);
        }
        .liste { display: flex; flex-direction: column; gap: 2px; margin: 8px 0; }
        .liste .leer { font-size: .8rem; color: var(--secondary-text-color); }
        .zeile {
          display: flex; align-items: center; gap: 6px; padding: 6px 2px;
          border-bottom: 1px solid var(--divider-color); font-size: .78rem;
        }
        .zeile:last-child { border-bottom: none; }
        .z-datum {
          flex: 0 0 auto; white-space: nowrap;
          color: var(--secondary-text-color); font-variant-numeric: tabular-nums;
        }
        .z-text {
          flex: 1; text-align: right; font-variant-numeric: tabular-nums;
        }
        .z-weg {
          flex: 0 0 auto; width: 26px; height: 26px; border-radius: 8px;
          cursor: pointer; line-height: 1; font-size: .85rem;
          border: 1px solid var(--divider-color);
          background: var(--card-background-color); color: var(--lpg-alarm, #e23c34);
        }
        .z-weg:hover { background: var(--secondary-background-color); }
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

        <div id="jahrblock" hidden>
          <div class="abschnitt">
            <span id="jahr-titel">Verbrauch</span>
            <span id="jahr-zusatz"></span>
          </div>
          <div class="jahr" id="jahr"></div>
        </div>

        <div id="preisblock" hidden>
          <div class="abschnitt">
            <span>Preisentwicklung</span>
            <span id="preis-spanne"></span>
          </div>
          <svg id="preise" viewBox="0 0 420 104" role="img" aria-label="Preisentwicklung"></svg>
        </div>

        <div class="fuss" id="fuss"></div>

        <div class="formular" id="formular" hidden>
          <div class="schalter">
            <button id="m-liefermenge" aria-pressed="true">Getankt</button>
            <button id="m-tankuhr" aria-pressed="false">Tankuhr</button>
            <button id="m-nachtragen" aria-pressed="false">Nachtragen</button>
            <button id="m-verlauf" aria-pressed="false">Korrigieren</button>
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
            <div class="feld" style="margin-top:8px">
              <label for="f-preis">Preis je Liter (EUR, optional)</label>
              <input id="f-preis" type="number" min="0" step="0.001" inputmode="decimal" placeholder="z. B. 0,677">
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

          <div id="block-nachtragen" hidden>
            <div class="feld">
              <label for="n-liter">Liefermenge (Liter, optional)</label>
              <input id="n-liter" type="number" min="0" step="1" inputmode="decimal" placeholder="z. B. 2500">
            </div>
            <div class="feld" style="margin-top:8px">
              <label for="n-preis">Damals bezahlter Preis (EUR/L)</label>
              <input id="n-preis" type="number" min="0" step="0.001" inputmode="decimal" placeholder="z. B. 0,638">
            </div>
            <div class="hinweis">
              Trägt eine zurückliegende Lieferung nur in die Historie ein – für den
              Preisverlauf. Füllstand und Verbrauchszählung bleiben unberührt.
            </div>
          </div>

          <div id="block-verlauf" hidden>
            <button id="v-rueckgaengig" class="ruecknahme" hidden></button>
            <div class="liste" id="v-liste"></div>
            <div class="hinweis">
              Löschen entfernt einen Eintrag nur aus dieser Liste und aus dem
              Preisverlauf – der Füllstand bleibt, wie er ist. Wer sich beim
              Tanken oder an der Tankuhr vertippt hat, nimmt die Aktion oben
              zurück: das stellt Füllstand und Zählung mit wieder her, auch
              Tage später.
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
     "kacheln", "fuss", "formular", "knopf-form", "preisblock", "preise", "preis-spanne",
     "jahrblock", "jahr", "jahr-titel", "jahr-zusatz",
     "m-liefermenge", "m-tankuhr", "m-nachtragen", "m-verlauf",
     "block-liefermenge", "block-tankuhr", "block-nachtragen", "block-verlauf",
     "block-datum", "v-liste", "v-rueckgaengig",
     "n-liter", "n-preis",
     "f-liter", "f-vorher", "f-preis", "f-prozent", "f-datum", "f-abbrechen", "f-speichern"]
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
      MODI.forEach((k) => {
        e[`m-${k}`].setAttribute("aria-pressed", String(m === k));
        e[`block-${k}`].hidden = m !== k;
      });
      // Bei der Tankuhr zählt der Moment des Ablesens, nicht ein wählbares
      // Datum; im Verlauf wird nichts eingetragen, sondern nur korrigiert.
      e["block-datum"].hidden = m === "tankuhr" || m === "verlauf";
      e["f-speichern"].hidden = m === "verlauf";
      if (m === "verlauf") this._verlaufListe();
    };
    MODI.forEach((k) => e[`m-${k}`].addEventListener("click", () => modus(k)));

    e["v-rueckgaengig"].addEventListener("click", () => this._rueckgaengig());
    e["f-speichern"].addEventListener("click", () => this._speichern());

    // Fadenkreuz im Preisdiagramm. Einmal gebunden, die Zeichnung darin wird
    // bei jeder Aktualisierung neu aufgebaut.
    if (e.preise) {
      ["pointerdown", "pointermove"].forEach((typ) =>
        e.preise.addEventListener(typ, (ev) => this._preisMarker(ev)));
      ["pointerleave", "pointercancel"].forEach((typ) =>
        e.preise.addEventListener(typ, () => this._preisMarkerAus()));
    }
  }

  /* ------------------------------------------------------------ Aktionen */

  _speichern() {
    const e = this._el;
    const ziel = this._ent.inhalt;
    if (!ziel) return;

    if (this._modus === "nachtragen") {
      const datum = e["f-datum"].value;
      const preis = parseFloat(e["n-preis"].value);
      const liter = parseFloat(e["n-liter"].value);
      if (!datum) return this._blinken(e["f-datum"]);
      if (isNaN(preis) && isNaN(liter)) return this._blinken(e["n-preis"]);
      const daten = { datum };
      if (!isNaN(liter)) daten.liter = liter;
      if (!isNaN(preis)) daten.preis_pro_liter = preis;
      this._hass.callService("fluessiggas", "lieferung_nachtragen", daten,
        { entity_id: ziel });
    } else if (this._modus === "tankuhr") {
      const p = parseFloat(e["f-prozent"].value);
      if (isNaN(p)) return this._blinken(e["f-prozent"]);
      this._hass.callService("fluessiggas", "fuellstand_setzen",
        { prozent: p }, { entity_id: ziel });
    } else {
      const liter = parseFloat(e["f-liter"].value);
      const vorher = parseFloat(e["f-vorher"].value);
      const preis = parseFloat(e["f-preis"].value);
      if (isNaN(liter) && isNaN(vorher)) return this._blinken(e["f-liter"]);
      const daten = {};
      if (!isNaN(liter)) daten.liter = liter;
      if (!isNaN(vorher)) daten.fuellstand_vorher_prozent = vorher;
      if (!isNaN(preis)) daten.preis_pro_liter = preis;
      if (e["f-datum"].value) daten.datum = e["f-datum"].value;
      this._hass.callService("fluessiggas", "betankung", daten, { entity_id: ziel });
    }

    ["f-liter", "f-vorher", "f-preis", "f-prozent", "n-liter", "n-preis"]
      .forEach((k) => { e[k].value = ""; });
    e["knopf-form"].click();
  }

  /* --------------------------------------------------- Korrigieren */

  /**
   * Liste der eingetragenen Lieferungen, jüngste zuerst, mit Löschknopf je
   * Zeile. Angesprochen wird jeder Eintrag über seine "id" aus der
   * Integration - zwei Lieferungen am selben Tag wären über das Datum
   * allein nicht zu unterscheiden.
   */
  _verlaufListe() {
    const e = this._el;
    if (!e["v-liste"]) return;
    const letzte = this._zustand("letzte_betankung");
    const attr = (letzte && letzte.attributes) || {};
    const eintraege = (attr.lieferungen || []).slice().reverse();

    const zurueck = attr.rueckgaengig;
    e["v-rueckgaengig"].hidden = !zurueck;
    if (zurueck) e["v-rueckgaengig"].textContent = `↶ Rückgängig: ${zurueck}`;

    if (!eintraege.length) {
      e["v-liste"].innerHTML =
        `<div class="leer">Noch keine Lieferung eingetragen.</div>`;
      return;
    }

    e["v-liste"].innerHTML = eintraege.map((eintrag, i) => {
      const teile = [];
      if (eintrag.liter != null) teile.push(this._fmt(eintrag.liter, 0, "L"));
      if (eintrag.preis_pro_liter != null) {
        teile.push(this._fmt(eintrag.preis_pro_liter, 3, "€/L"));
      }
      if (eintrag.kosten != null) teile.push(this._fmt(eintrag.kosten, 0, "€"));
      if (eintrag.faktor_neu) {
        teile.push(`kalibriert ${this._fmt(eintrag.faktor_alt, 3)} → ` +
          `${this._fmt(eintrag.faktor_neu, 3, "L/m³")}`);
      }
      if (eintrag.nachgetragen) teile.push("nachgetragen");
      const datum = this._parse(String(eintrag.datum || ""));
      return `<div class="zeile">
          <span class="z-datum">${datum ? this._datumText(datum) : "?"}</span>
          <span class="z-text">${teile.join(" · ") || "ohne Angaben"}</span>
          <button class="z-weg" data-i="${i}" title="Eintrag löschen"
                  aria-label="Eintrag löschen">✕</button>
        </div>`;
    }).join("");

    e["v-liste"].querySelectorAll(".z-weg").forEach((knopf) => {
      const eintrag = eintraege[parseInt(knopf.dataset.i, 10)];
      knopf.addEventListener("click", () => this._loeschen(eintrag, knopf));
    });
  }

  _loeschen(eintrag, knopf) {
    const ziel = this._ent.inhalt;
    if (!ziel || !eintrag) return;
    const daten = eintrag.id ? { eintrag: eintrag.id } : { datum: eintrag.datum };
    this._hass.callService("fluessiggas", "lieferung_loeschen", daten,
      { entity_id: ziel });
    // Die Liste zeichnet sich erst mit dem nächsten Zustandsupdate neu; bis
    // dahin die Zeile abblenden, damit der Klick sichtbar ankommt.
    const zeile = knopf && knopf.closest(".zeile");
    if (zeile) zeile.style.opacity = "0.35";
  }

  _rueckgaengig() {
    const ziel = this._ent.inhalt;
    if (!ziel) return;
    this._hass.callService("fluessiggas", "rueckgaengig", {}, { entity_id: ziel });
    this._el["v-rueckgaengig"].hidden = true;
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

  _datum(kennung) {
    const z = this._zustand(kennung);
    if (!istWert(z)) return null;
    return this._parse(z.state);
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
    const e = this._el;
    if (!this._hass || !e) return;

    const inhalt = this._zustand("inhalt");

    // ---------------------------------------------------------- Hinweise
    if (!inhalt) {
      e.fehler.hidden = false;
      e.fehler.innerHTML = this._tanks.size
        ? `Kein Tank gefunden, der zu <code>tank: ${c.tank}</code> passt. ` +
          `Vorhanden: ${[...this._tanks].map((t) => `<code>${t}</code>`).join(", ")}`
        : "Keine Flüssiggastank-Integration gefunden. Ist sie unter " +
          "<b>Einstellungen → Geräte &amp; Dienste</b> eingerichtet?";
      e.grafik.style.opacity = ".35";
      e.kacheln.innerHTML = "";
      e.fuss.textContent = "";
      e.verlauf.hidden = true;
      e["t-prozent"].textContent = "–";
      e["t-liter"].textContent = "";
      return;
    }
    if (this._tanks.size > 1 && !c.tank) {
      e.fehler.hidden = false;
      e.fehler.innerHTML =
        "Mehrere Tanks eingerichtet – bitte in der Karte <code>tank: &lt;Name&gt;</code> angeben. " +
        `Angezeigt wird ${inhalt.attributes.friendly_name || this._ent.inhalt}.`;
    } else {
      e.fehler.hidden = true;
    }
    e.grafik.style.opacity = "1";

    const a = inhalt.attributes || {};
    e.titel.textContent =
      c.name || (a.friendly_name || "Flüssiggastank").replace(/\s+\S+$/, "") || "Flüssiggastank";

    // ---------------------------------------------------------- Werte
    const liter = zahl(inhalt, 0);
    const nenn = a.nennvolumen || 4850;
    const nutzbar = a.nutzbares_volumen || nenn * 0.85;
    const reserve = a.reserve || 0;
    const prozent = zahl(this._zustand("inhalt_prozent"), (liter / Math.max(nenn, 1)) * 100);

    // Rot hängt an der Reserve statt an einer eigenen Zahl – sonst könnten
    // Farbe und Bestellfrist auseinanderlaufen. Gelb ist einstellbar.
    const warnAb = a.warnschwelle_prozent != null ? Number(a.warnschwelle_prozent) : 30;
    const farbe =
      (reserve > 0 && liter <= reserve) ? "var(--lpg-alarm)"
      : (prozent <= warnAb) ? "var(--lpg-warn)"
      : "var(--lpg-gut)";
    this.style.setProperty("--lpg-farbe", farbe);

    // ---------------------------------------------------------- Tankgrafik
    const yOben = 48, yUnten = 168, hoehe = yUnten - yOben;
    const yFuer = (anteil) => yUnten - fuellhoehe(Math.max(0, Math.min(1, anteil))) * hoehe;

    e.liquid.setAttribute("transform", `translate(0,${yFuer(prozent / 100).toFixed(2)})`);

    const maxProzent = (nutzbar / Math.max(nenn, 1)) * 100;
    const yMax = yFuer(maxProzent / 100);
    e["marke-max"].setAttribute("y1", yMax); e["marke-max"].setAttribute("y2", yMax);
    e["marke-max-text"].setAttribute("y", yMax);
    e["marke-max-text"].textContent = `${this._fmt(maxProzent, 0)} %`;

    const zeigeReserve = reserve > 0 && reserve < nutzbar;
    const yRes = yFuer(reserve / Math.max(nenn, 1));
    ["marke-reserve", "marke-reserve-text"].forEach((k) => {
      e[k].style.display = zeigeReserve ? "" : "none";
    });
    if (zeigeReserve) {
      e["marke-reserve"].setAttribute("y1", yRes); e["marke-reserve"].setAttribute("y2", yRes);
      e["marke-reserve-text"].setAttribute("y", yRes);
    }

    const energie = zahl(this._zustand("restenergie"), null);
    e["t-prozent"].textContent = `${this._fmt(prozent, 1)} %`;
    e["t-liter"].textContent =
      `${this._fmt(liter, 0)} von ${this._fmt(nutzbar, 0)} L` +
      (energie !== null ? ` · ${this._fmt(energie, 0)} kWh` : "");

    this._verlaufZeichnen(reserve, nenn);

    // ---------------------------------------------------------- Kacheln
    const leerAm = this._datum("leer_am");
    const bestellen = this._datum("bestellen_bis");
    const wert = zahl(this._zustand("restwert"), null);
    const proTag = zahl(this._zustand("tagesverbrauch"), null);

    const reserveAm = this._datum("reserve_am");
    const jahr = zahl(this._zustand("jahresverbrauch"), null);
    const seitZ = this._zustand("verbrauch_seit_betankung");
    const seit = zahl(seitZ, null);
    const seitTage = istWert(seitZ) ? (seitZ.attributes || {}).tage : null;
    const kacheln = [
      { label: "Restenergie", wert: this._fmt(energie, 0, "kWh"),
        zusatz: wert !== null ? this._fmt(wert, 0, "EUR") : "", kennung: "restenergie" },
      { label: "Ø Verbrauch", wert: this._fmt(proTag, 1, "L/d"),
        zusatz: jahr !== null ? this._erwartet(jahr)
          : (proTag !== null ? this._fmt(proTag * 30, 0, "L/Monat") : ""),
        kennung: jahr !== null ? "jahresverbrauch" : "tagesverbrauch" },
      // Eine Kachel "Reichweite" gab es hier auch mal. Die Tage stehen aber
      // schon unter "Reserve erreicht" und "Voraussichtlich leer" - der
      // Platz gehört jetzt dem Verbrauch seit der Betankung, der sonst
      // nirgends auf der Karte auftauchte.
      { label: "Seit Betankung", wert: this._fmt(seit, 0, "L"),
        zusatz: seitTage >= 1 ? `über ${this._fmt(seitTage, 0)} Tage` : "",
        kennung: "verbrauch_seit_betankung" },
      { label: "Reserve erreicht", wert: this._datumText(reserveAm),
        zusatz: this._inTagen(reserveAm), kennung: "reserve_am" },
      { label: "Voraussichtlich leer", wert: this._datumText(leerAm),
        zusatz: this._inTagen(leerAm), kennung: "leer_am" },
      { label: "Bestellen bis", wert: this._datumText(bestellen),
        zusatz: this._inTagen(bestellen, "überfällig"), kennung: "bestellen_bis" },
    ];

    this._kachelnZeichnen(e.kacheln, kacheln);
    this._jahrZeichnen();

    // ---------------------------------------------------------- Fußzeile
    const letzte = this._zustand("letzte_betankung");
    const teile = [];
    if (istWert(letzte)) {
      const menge = letzte.attributes && letzte.attributes.liter;
      teile.push(`Letzte Betankung: ${this._datumText(this._parse(letzte.state))}` +
        (menge ? ` (${this._fmt(menge, 0, "L")})` : ""));
    }
    const preis = zahl(this._zustand("gaspreis"), null);
    if (preis !== null) teile.push(`Gaspreis: ${this._fmt(preis, 3, "EUR/L")}`);

    // Der Umrechnungsfaktor nur dort, wo er etwas bedeutet: Bei kWh- oder
    // Liter-Zählern wird gar nicht über m³ gerechnet.
    const faktor = this._zustand("umrechnungsfaktor");
    const fa = (faktor && faktor.attributes) || {};
    if (istWert(faktor) && fa.kalibrierbar) {
      teile.push(`Umrechnung: ${this._fmt(zahl(faktor), 3, "L/m³")}` +
        (fa.kalibrierungen ? " (kalibriert)" : ""));
    }
    e.fuss.textContent = teile.join(" · ");

    this._preisverlaufZeichnen(letzte);
    if (this._modus === "verlauf" && this._formOffen) this._verlaufListe();
  }


  /**
   * Kacheln in ein Gitter zeichnen; ein Klick öffnet die Entität dahinter.
   * `zusatz: null` lässt die dritte Zeile ganz weg - sonst hält ein leeres
   * &nbsp; die Kachel unnötig hoch.
   */
  _kachelnZeichnen(ziel, kacheln) {
    ziel.innerHTML = kacheln.map((k, i) => `
      <button class="kachel" data-i="${i}">
        <span class="k-label">${k.label}</span>
        <span class="k-wert">${k.wert}</span>` +
      (k.zusatz === null ? "" : `
        <span class="k-zusatz">${k.zusatz || "&nbsp;"}</span>`) + `
      </button>`).join("");
    ziel.querySelectorAll(".kachel").forEach((el) => {
      const kennung = kacheln[parseInt(el.dataset.i, 10)].kennung;
      el.addEventListener("click", () => this._mehrInfo(this._ent[kennung]));
    });
  }

  /**
   * Der erwartete Jahresverbrauch in Litern und Kubikmetern. Die m³ kommen
   * fertig aus der Integration, damit die Karte den Faktor nicht selbst
   * anwenden muss - der kalibriert sich schließlich nach.
   */
  _erwartet(liter) {
    const attr = (this._zustand("jahresverbrauch") || {}).attributes || {};
    const kubik = attr.kubikmeter;
    // Eine Nachkommastelle bei den m³: Ein ganzer Kubikmeter sind rund
    // 3,9 Liter - auf ganze m³ gerundet wäre die Anzeige um bis zu zwei
    // Liter daneben, und das fällt beim Vergleich mit der Literzahl auf.
    return `erw. ${this._fmt(liter, 0, "L")}` +
      (kubik != null ? ` · ${this._fmt(kubik, 1, "m³")}` : "") + "/Jahr";
  }

  /**
   * Verbrauch des laufenden Kalenderjahres in Liter, m³ und kWh - drei
   * eigene Entitäten, damit jede ihre Langzeitstatistik hat und sich
   * einzeln anklicken lässt.
   */
  _jahrZeichnen() {
    const e = this._el;
    if (!e.jahrblock) return;
    const liter = this._zustand("jahr_liter");
    if (!this._config.jahr || !istWert(liter)) { e.jahrblock.hidden = true; return; }
    e.jahrblock.hidden = false;

    const jahr = (liter.attributes || {}).jahr;
    e["jahr-titel"].textContent = jahr ? `Verbrauch ${jahr}` : "Verbrauch dieses Jahr";

    // Bewusst nicht "x % des Jahres": Der verheizte Anteil läuft dem Kalender
    // erst voraus und dann nachher (Anfang Mai knapp 49 % bei einem Drittel
    // Kalenderjahr, Anfang November 70 % bei 83 %). Verglichen wird deshalb
    // mit dem, was das Monatsprofil bis heute erwartet hätte.
    const bisher = zahl(liter, null);
    const erwartet = (liter.attributes || {}).erwartet_bis_heute;
    e["jahr-zusatz"].textContent = erwartet
      ? `erwartet bis heute ${this._fmt(erwartet, 0, "L")} ` +
        `(${bisher >= erwartet ? "+" : "−"}${this._fmt(
          Math.abs((bisher / erwartet - 1) * 100), 0, "%")})`
      : "";

    this._kachelnZeichnen(e.jahr, [
      { label: "Liter", wert: this._fmt(bisher, 0, "L"),
        zusatz: null, kennung: "jahr_liter" },
      { label: "Kubik", wert: this._fmt(zahl(this._zustand("jahr_kubik"), null), 1, "m³"),
        zusatz: null, kennung: "jahr_kubik" },
      { label: "Energie", wert: this._fmt(zahl(this._zustand("jahr_energie"), null), 0, "kWh"),
        zusatz: null, kennung: "jahr_energie" },
    ]);
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
    const prog = this._zustand("reichweite");
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

  /**
   * Preisentwicklung aus der Lieferhistorie. Bewusst die tatsächlich bezahlten
   * Preise und nicht der laufende Marktpreis – das ist die Reihe, die zeigt,
   * ob man gut eingekauft hat.
   */
  _preisverlaufZeichnen(letzte) {
    const block = this._el.preisblock;
    const svg = this._el.preise;
    if (!block || !svg) return;
    const c = this._config;

    // Linie: bevorzugt die Langzeitstatistik des konfigurierten Preis-Sensors,
    // sonst die eigenen Lieferungen. Die Betankungen liegen als Punkte oben
    // drauf - man sieht damit, ob man über oder unter dem Verlauf gekauft hat.
    const attr = (this._zustand("gaspreis") || {}).attributes || {};
    const statistik = (attr.preisverlauf || [])
      .map((p) => ({ t: this._monat(p.monat), preis: parseFloat(p.preis) }))
      .filter((p) => p.t && !isNaN(p.preis));

    const lieferungen = ((letzte && letzte.attributes && letzte.attributes.lieferungen) || [])
      .map((l) => ({
        datum: l && l.datum ? this._parse(l.datum) : null,
        preis: parseFloat(l && l.preis_pro_liter),
        liter: l && l.liter,
      }))
      .filter((l) => l.datum && !isNaN(l.preis))
      .map((l) => ({ t: l.datum.getTime(), preis: l.preis, liter: l.liter, tanken: true }))
      .sort((a, b) => a.t - b.t);

    const ausStatistik = statistik.length >= 2;
    const linie = (ausStatistik ? statistik : lieferungen).slice().sort((a, b) => a.t - b.t);
    if (!c.preisverlauf || linie.length < 2) {
      block.hidden = true;
      this._preisDaten = null;
      return;
    }
    block.hidden = false;

    const alle = linie.concat(lieferungen);
    const tMin = Math.min(...alle.map((p) => p.t));
    const tMax = Math.max(...alle.map((p) => p.t));
    const tSpanne = Math.max(tMax - tMin, 86400000);
    const preise = alle.map((p) => p.preis);
    const min = Math.min(...preise), max = Math.max(...preise);
    const spanne = Math.max(max - min, 0.01);

    const B = 420, H = 116, l = 34, r = 8, o = 12, u = 26;
    const x = (t) => l + ((t - tMin) / tSpanne) * (B - l - r);
    const y = (v) => o + (1 - (v - min + spanne * 0.15) / (spanne * 1.3)) * (H - o - u);

    const pfad = linie
      .map((p, i) => `${i ? "L" : "M"} ${x(p.t).toFixed(1)},${y(p.preis).toFixed(1)}`)
      .join(" ");
    const schnitt = linie.reduce((a, p) => a + p.preis, 0) / linie.length;

    const punkte = lieferungen.map((p) =>
      `<circle class="p-punkt-letzt" cx="${x(p.t).toFixed(1)}" cy="${y(p.preis).toFixed(1)}" r="4"/>`
    ).join("");

    // Jede Betankung bekommt ihr Datum an die Achse - übersprungen nur, wo es
    // sich sonst überlappen würde. Ohne Betankungen die Spanne der Linie.
    const lang = (this._hass.locale && this._hass.locale.language) || "de";
    const kurz = (t) => new Date(t).toLocaleDateString(lang, { month: "2-digit", year: "2-digit" });
    let beschriftung = "";
    if (lieferungen.length) {
      let letztesX = -999;
      beschriftung = lieferungen.map((p) => {
        const px = Math.min(Math.max(x(p.t), l + 12), B - r - 12);
        if (px - letztesX < 38) return "";
        letztesX = px;
        return `<text class="p-text" x="${px.toFixed(1)}" y="${H - 6}" text-anchor="middle">${kurz(p.t)}</text>`;
      }).join("");
    } else {
      beschriftung =
        `<text class="p-text" x="${l}" y="${H - 6}">${kurz(tMin)}</text>` +
        `<text class="p-text" x="${B - r}" y="${H - 6}" text-anchor="end">${kurz(tMax)}</text>`;
    }

    svg.setAttribute("viewBox", `0 0 ${B} ${H}`);
    svg.innerHTML = `
      <line class="p-schnitt" x1="${l}" y1="${y(schnitt).toFixed(1)}" x2="${B - r}" y2="${y(schnitt).toFixed(1)}"/>
      <text class="p-text" x="${l - 4}" y="${(y(max) + 3).toFixed(1)}" text-anchor="end">${this._fmt(max, 2)}</text>
      <text class="p-text" x="${l - 4}" y="${(y(min) + 3).toFixed(1)}" text-anchor="end">${this._fmt(min, 2)}</text>
      <path class="p-linie" d="${pfad}"/>${punkte}${beschriftung}
      <g id="p-marker"></g>
      <rect id="p-hit" x="${l}" y="0" width="${(B - l - r).toFixed(1)}" height="${H - u}"
            fill="transparent" style="cursor:crosshair;touch-action:none"/>`;

    // Für das Fadenkreuz: Skalen und Punkte merken, die Zeichnung wird ja bei
    // jeder Zustandsänderung neu aufgebaut.
    this._preisDaten = { punkte: alle.slice().sort((a, b) => a.t - b.t), x, y, B, H, l, r, u };

    const anzahl = lieferungen.length;
    this._el["preis-spanne"].textContent = (ausStatistik ? "Statistik · " : "") +
      `${anzahl} ${anzahl === 1 ? "Lieferung" : "Lieferungen"} · Ø ${this._fmt(schnitt, 3, "EUR/L")}`;
  }

  /**
   * Fadenkreuz wie im Verlaufsdiagramm von Home Assistant: senkrechte Linie am
   * nächstgelegenen Datenpunkt, dazu Datum, Preis und - bei einer Betankung -
   * die Menge.
   */
  _preisMarker(ev) {
    const d = this._preisDaten;
    const svg = this._el.preise;
    if (!d || !svg) return;
    const marker = svg.querySelector("#p-marker");
    if (!marker) return;

    const kasten = svg.getBoundingClientRect();
    if (!kasten.width) return;
    const ux = ((ev.clientX - kasten.left) / kasten.width) * d.B;

    let treffer = null, abstand = Infinity;
    for (const p of d.punkte) {
      const dist = Math.abs(d.x(p.t) - ux);
      // Betankungen gewinnen bei Gleichstand - sie sind die interessantere Zahl
      if (dist < abstand || (dist === abstand && p.tanken)) { abstand = dist; treffer = p; }
    }
    if (!treffer) return;

    const px = d.x(treffer.t), py = d.y(treffer.preis);
    const lang = (this._hass.locale && this._hass.locale.language) || "de";
    const text = new Date(treffer.t).toLocaleDateString(lang, {
      day: "2-digit", month: "2-digit", year: "numeric",
    }) + " · " + this._fmt(treffer.preis, 3, "EUR/L") +
      (treffer.liter ? ` · ${this._fmt(treffer.liter, 0, "L")}` : "");

    // Kasten links vom Punkt, wenn rechts kein Platz mehr ist, und in jedem
    // Fall innerhalb der Zeichenfläche
    const breite = Math.max(text.length * 5.6 + 14, 96);
    const bx = Math.min(
      Math.max(px + breite + 8 > d.B - d.r ? px - breite - 6 : px + 6, 2),
      d.B - breite - 2,
    );

    marker.innerHTML = `
      <line class="p-kreuz" x1="${px.toFixed(1)}" y1="6" x2="${px.toFixed(1)}" y2="${d.H - d.u}"/>
      <circle class="p-treffer" cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="5"/>
      <rect class="p-box" x="${bx.toFixed(1)}" y="4" width="${breite.toFixed(1)}" height="19" rx="5"/>
      <text class="p-boxtext" x="${(bx + 6).toFixed(1)}" y="17">${text}</text>`;
  }

  _preisMarkerAus() {
    const svg = this._el.preise;
    const marker = svg && svg.querySelector("#p-marker");
    if (marker) marker.innerHTML = "";
  }


  /** "2024-01" auf die Monatsmitte legen, damit die Punkte mittig sitzen. */
  _monat(text) {
    const treffer = /^(\d{4})-(\d{2})$/.exec(String(text || ""));
    return treffer ? new Date(Number(treffer[1]), Number(treffer[2]) - 1, 15).getTime() : null;
  }


  /** "in 74 Tagen" bzw. "heute" / "überfällig seit 3 Tagen". */
  _inTagen(d, ueberfaellig = "vorbei") {
    if (!d) return "";
    const tage = Math.round((d - new Date()) / 86400000);
    if (tage === 0) return "heute";
    return tage > 0 ? `in ${tage} Tagen` : `${ueberfaellig} seit ${Math.abs(tage)} Tagen`;
  }

  _wochentag(d) {
    const lang = (this._hass && this._hass.locale && this._hass.locale.language) || "de";
    const tage = Math.round((d - new Date()) / 86400000);
    return `${d.toLocaleDateString(lang, { weekday: "long" })} · in ${tage} Tagen`;
  }
}

// Anmelden mit try/catch statt mit einer Abfrage über customElements.get().
//
// Home Assistant installiert scoped-custom-element-registry, einen Polyfill,
// der window.customElements ersetzt. Dessen get() und whenDefined() kennen
// ausschließlich die eigene Map. Ein get() als Wächter kann deshalb "nicht
// angemeldet" melden, obwohl die Karte in der nativen Registry längst steht -
// und dann bliebe die Anmeldung in der Registry aus, die Lovelace befragt.
//
// Ein Doppeleintrag in derselben Registry wirft, und das wird hier geschluckt.
// Ungefangen würde er die Ausführung des Moduls abbrechen - dann fehlte alles,
// was danach kommt. Genau so verabschieden sich andere Karten im Protokoll.
try {
  customElements.define("lpg-tank-card", LpgTankCard);
} catch (fehler) {
  // Schon in dieser Registry angemeldet. Nichts zu tun.
}

// Eintrag in der Kartenauswahl, ohne Dublette bei doppelter Ausführung
window.customCards = window.customCards || [];
if (!window.customCards.some((karte) => karte.type === "lpg-tank-card")) {
  window.customCards.push({
    type: "lpg-tank-card",
    name: "Flüssiggastank",
    preview: false,
    description: "Grafischer Füllstand eines liegenden Flüssiggastanks inkl. Leer-Prognose und Betankungseingabe.",
    documentationURL: "https://github.com/tach2004/ha-fluessiggasverbrauch",
  });
}

console.info(
  `%c LPG-TANK-CARD %c ${LPG_VERSION} `,
  "color:#fff;background:#2f7fd6;font-weight:700",
  "color:#2f7fd6;background:#eee"
);
