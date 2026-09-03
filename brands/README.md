# Logo für den Integrations-Katalog

`icon.svg` ist die Quelle, `icon.png` (256×256) und `icon@2x.png` (512×512) sind
daraus gerendert – PNG mit Transparenz, wie es der Katalog verlangt.

## Warum liegt das hier und nicht in der Integration?

Home Assistant lädt die Logos, die im Dialog **Integration hinzufügen** und in
der Geräteübersicht erscheinen, ausschließlich von `brands.home-assistant.io`.
Eine Integration kann ihr eigenes Logo **nicht** mitliefern – custom
integrations bekommen deshalb standardmäßig das Puzzleteil-Symbol.

Was die Integration sehr wohl selbst bestimmt, sind die Symbole ihrer
Entitäten und Dienste; die stehen in
[`../custom_components/fluessiggas/icons.json`](../custom_components/fluessiggas/icons.json)
und wirken sofort.

## Eintragen lassen

1. [`home-assistant/brands`](https://github.com/home-assistant/brands) forken.
2. `custom_integrations/fluessiggas/icon.png` und `icon@2x.png` aus diesem
   Ordner übernehmen.
3. Pull Request stellen.

Zwei Bedingungen sind dabei zu beachten: Der Ordnername muss exakt der Domain
entsprechen (`fluessiggas`), und die Integration muss öffentlich erreichbar
sein. **Solange dieses Repository privat ist, wird der Pull Request abgelehnt.**

## Neu rendern

```bash
chromium --headless --default-background-color=00000000 \
  --force-device-scale-factor=1 --window-size=256,256 \
  --screenshot=icon.png datei-mit-dem-svg.html
```
