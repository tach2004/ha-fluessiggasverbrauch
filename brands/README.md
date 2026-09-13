# Marke

`icon.svg` ist die Quelle. Daraus entstehen die beiden PNG-Dateien, die die
Integration ausliefert:
[`../custom_components/fluessiggas/brand/`](../custom_components/fluessiggas/brand/) –
`icon.png` mit 256 × 256 und `icon@2x.png` mit 512 × 512, mit transparentem
Hintergrund.

## Warum dieser Ordner ausgeliefert wird

Seit Home Assistant **2026.3** darf eine Integration ihr Logo selbst
mitbringen. Home Assistant erkennt eine Integration als „hat eine Marke",
wenn neben ihren Modulen ein Ordner `brand` liegt
(`Integration.has_branding` ist schlicht `"brand" in _top_level_files`), und
reicht dessen Bilder unter

```
/api/brands/integration/fluessiggas/icon.png
```

heraus. Der Dialog *Integration hinzufügen* zeigen damit dieses
Symbol statt des Puzzleteils.

Bis 2026.2 ging das nicht – Logos kamen ausschließlich von
`brands.home-assistant.io`, und eine custom integration musste dort per Pull
Request eingetragen werden. Genau das stand vorher auch hier. Der Ordner
`custom_integrations` in
[home-assistant/brands](https://github.com/home-assistant/brands) ist deshalb
inzwischen als veraltet markiert.

## Wer auf einer älteren Fassung ist

Unter Home Assistant 2026.3 bleibt das Puzzleteil. Wer das auch dort ändern
will, trägt die Domain zusätzlich in
[home-assistant/brands](https://github.com/home-assistant/brands) ein und lädt
die beiden PNG-Dateien aus `custom_components/fluessiggas/brand/` dorthin
hoch. Nötig ist das nicht.

Was die Integration ohnehin selbst bestimmt, sind die Symbole ihrer Entitäten
und Dienste; die stehen in
[`../custom_components/fluessiggas/icons.json`](../custom_components/fluessiggas/icons.json).
