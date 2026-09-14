# Marke

`icon.svg` ist die Quelle. Daraus entstehen die beiden PNG-Dateien, die die
Integration ausliefert:
[`../custom_components/fluessiggas/brand/`](../custom_components/fluessiggas/brand/) –
`icon.png` mit 256 × 256 und `icon@2x.png` mit 512 × 512, mit transparentem
Hintergrund. Beide Maße entsprechen den Vorgaben von
[home-assistant/brands](https://github.com/home-assistant/brands).

## In Home Assistant: der lokale Ordner genügt

Seit Home Assistant **2026.3** darf eine Integration ihr Logo selbst
mitbringen. Home Assistant erkennt eine Integration als „hat eine Marke",
wenn neben ihren Modulen ein Ordner `brand` liegt
(`Integration.has_branding` ist schlicht `"brand" in _top_level_files`), und
reicht dessen Bilder unter

```
/api/brands/integration/fluessiggas/icon.png
```

heraus. Unter *Einstellungen → Geräte & Dienste* und im Dialog *Integration
hinzufügen* erscheint damit dieses Symbol. Bis 2026.2 ging das nicht – Logos
kamen ausschließlich von `brands.home-assistant.io`.

## In HACS: der lokale Ordner genügt **nicht**

Das stand hier vorher falsch, deshalb ausführlich. HACS zeigt das lokale Logo
**nicht**, und es zeigt auch kein Ersatzsymbol – die Spalte bleibt leer.

HACS zeichnet das Symbol in
[`src/dashboards/hacs-dashboard.ts`](https://github.com/hacs/frontend/blob/main/src/dashboards/hacs-dashboard.ts):

```ts
repository.category === "integration"
  ? html`<img src=${brandsUrl({ domain, type: "icon", useFallback: true })} />`
  : html`<ha-svg-icon .path=${typeIcon(repository.category)}></ha-svg-icon>`
```

Zwei Dinge stecken darin:

1. **Die URL zeigt auf die CDN, nicht auf Home Assistant.** HACS bindet das
   HA-Frontend als festgepinntes Git-Submodul ein, Commit `3ffbd435` vom
   **9. Januar 2025**. In dieser Fassung liefert `brandsUrl()`
   `https://brands.home-assistant.io/_/<domain>/icon.png` – für eine nicht
   eingetragene Domain also einen 404. Die heutige HA-Fassung derselben
   Funktion zeigt dagegen auf `/api/brands/integration/<domain>/icon.png` und
   kennt den Parameter `useFallback` gar nicht mehr. HACS müsste sein Submodul
   nachziehen *und* den Aufruf anpassen.
2. **Es gibt keinen Fallback.** Das `<img>` hat kein `onerror`. Der
   `ha-svg-icon`-Zweig greift nur für andere Kategorien (Karten, Themes,
   Skripte). In HACS' eigener Symboltabelle
   ([`src/tools/type-icon.ts`](https://github.com/hacs/frontend/blob/main/src/tools/type-icon.ts))
   steht `integration: mdiPackageVariant` – für Integrationen ist dieser
   Eintrag toter Code. Ein 404 hinterlässt deshalb ein leeres Kästchen, kein
   Platzhaltersymbol.

Das vielzitierte Puzzleteil kommt aus Home Assistant selbst, nicht aus HACS.

## Damit das Symbol auch in HACS erscheint

Die Domain zusätzlich bei
[home-assistant/brands](https://github.com/home-assistant/brands) eintragen:
die beiden PNG-Dateien aus `custom_components/fluessiggas/brand/` unverändert
nach `custom_integrations/fluessiggas/` kopieren und einen Pull Request
stellen. Danach liefert die CDN-URL kein 404 mehr, und HACS zeigt dasselbe
Symbol.

Beide Wege beißen sich nicht: Home Assistant nimmt den lokalen Ordner, HACS
die CDN. Nötig ist der Eintrag nur für die Anzeige in HACS – funktional ändert
er nichts.

Was die Integration ohnehin selbst bestimmt, sind die Symbole ihrer Entitäten
und Dienste; die stehen in
[`../custom_components/fluessiggas/icons.json`](../custom_components/fluessiggas/icons.json).
