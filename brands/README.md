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

Das stand hier vorher falsch, deshalb ausführlich. In HACS steht bei der
Integration ein graues Kästchen mit der Aufschrift *„icon not available"*.

HACS zeichnet das Symbol in
[`src/dashboards/hacs-dashboard.ts`](https://github.com/hacs/frontend/blob/main/src/dashboards/hacs-dashboard.ts):

```ts
repository.category === "integration"
  ? html`<img src=${brandsUrl({ domain, type: "icon", useFallback: true })} />`
  : html`<ha-svg-icon .path=${typeIcon(repository.category)}></ha-svg-icon>`
```

**Die URL zeigt auf die CDN, nicht auf Home Assistant.** HACS bindet das
HA-Frontend als festgepinntes Git-Submodul ein, Commit `3ffbd435` vom
**9. Januar 2025**. In dieser Fassung liefert `brandsUrl()`
`https://brands.home-assistant.io/_/<domain>/icon.png`. Die heutige HA-Fassung
derselben Funktion zeigt dagegen auf
`/api/brands/integration/<domain>/icon.png` und kennt den Parameter
`useFallback` gar nicht mehr. HACS müsste sein Submodul nachziehen *und* den
Aufruf anpassen – von allein wird der lokale Ordner dort nicht gelesen.

**Das `_/` in der URL ist entscheidend** und der Grund, warum sich hier nichts
mit einem Fallback im Code reparieren lässt. Die
[brands-Doku](https://github.com/home-assistant/brands) dazu:

> A missing image will result in placeholder image being served telling the
> logo/icon is missing. This also applies to domains, in case the integration
> domain is missing.

Die CDN antwortet also mit **HTTP 200 und einem Platzhalterbild**, nicht mit
einem 404. Für HACS ist das Bild damit erfolgreich geladen; ein `onerror` am
`<img>` würde nie auslösen. Der Eintrag `integration: mdiPackageVariant` in
HACS' Symboltabelle
([`src/tools/type-icon.ts`](https://github.com/hacs/frontend/blob/main/src/tools/type-icon.ts))
bleibt für Integrationen unerreichbar – erreichbar ist er nur für Karten,
Themes und Skripte.

Wer in HACS also graue Kategoriesymbole bei anderen Repositories sieht: Das
sind **Plugins** (Lovelace-Karten), nicht Integrationen ohne Logo. Eine
Integration zeigt immer entweder ihr Logo aus der CDN oder den
Platzhalter – ein Puzzleteil gibt es dort für sie nicht.

Das vielzitierte Puzzleteil kommt aus Home Assistant selbst, nicht aus HACS.

## Damit das Symbol auch in HACS erscheint

Dafür gibt es genau einen Weg: die Domain zusätzlich bei
[home-assistant/brands](https://github.com/home-assistant/brands) eintragen –
die beiden PNG-Dateien aus `custom_components/fluessiggas/brand/` unverändert
nach `custom_integrations/fluessiggas/` kopieren und einen Pull Request
stellen. Danach liefert die CDN-URL das echte Symbol statt des Platzhalters.

Beide Wege beißen sich nicht: Home Assistant nimmt den lokalen Ordner, HACS
die CDN. Nötig ist der Eintrag nur für die Anzeige in HACS – funktional ändert
er nichts.

Was die Integration ohnehin selbst bestimmt, sind die Symbole ihrer Entitäten
und Dienste; die stehen in
[`../custom_components/fluessiggas/icons.json`](../custom_components/fluessiggas/icons.json).
