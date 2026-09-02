#!/usr/bin/env python3
"""
Monatsprofil aus der Home-Assistant-Langzeitstatistik berechnen.

Die Prognose im Package braucht zwölf Zahlen: den mittleren Gasverbrauch je
Kalendermonat. Dieses Skript holt sich die Langzeitstatistik der angegebenen
Verbrauchssensoren über die WebSocket-API, mittelt sie über die gewünschte
Anzahl Jahre und schreibt das Ergebnis auf Wunsch direkt in die Helfer.

    pip install websockets

    python3 monatsprofil.py \
        --url http://homeassistant.local:8123 \
        --token <Langlebiges-Zugriffstoken> \
        --entities sensor.heizgas_dieses_jahr sensor.warmwassergas_dieses_jahr \
        --jahre 2

Mit --schreiben werden input_text.gastank_monatsmittel_liter und
input_text.gastank_monatszaehler gleich gesetzt.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from collections import defaultdict

MONATE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
          "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


class HaWs:
    """Dünner Wrapper um die WebSocket-API von Home Assistant."""

    def __init__(self, url: str, token: str):
        self.ws_url = url.rstrip("/").replace("https://", "wss://").replace("http://", "ws://")
        self.ws_url += "/api/websocket"
        self.token = token
        self._id = 0
        self._ws = None

    async def __aenter__(self):
        try:
            import websockets
        except ImportError:
            raise RuntimeError("Bitte zuerst installieren:  pip install websockets")
        self._ws = await websockets.connect(self.ws_url, max_size=32 * 1024 * 1024)
        hallo = json.loads(await self._ws.recv())
        if hallo.get("type") != "auth_required":
            raise RuntimeError(f"Unerwartete Begrüßung: {hallo}")
        await self._ws.send(json.dumps({"type": "auth", "access_token": self.token}))
        antwort = json.loads(await self._ws.recv())
        if antwort.get("type") != "auth_ok":
            raise RuntimeError(f"Anmeldung fehlgeschlagen: {antwort.get('message', antwort)}")
        return self

    async def __aexit__(self, *_):
        if self._ws:
            await self._ws.close()

    async def befehl(self, **daten):
        self._id += 1
        await self._ws.send(json.dumps({"id": self._id, **daten}))
        while True:
            nachricht = json.loads(await self._ws.recv())
            if nachricht.get("id") != self._id or nachricht.get("type") != "result":
                continue
            if not nachricht.get("success"):
                raise RuntimeError(nachricht.get("error", nachricht))
            return nachricht.get("result")


def als_datum(start) -> dt.datetime:
    """start kommt je nach HA-Version als ms-Zeitstempel oder ISO-String."""
    if isinstance(start, (int, float)):
        return dt.datetime.fromtimestamp(start / 1000, dt.timezone.utc)
    return dt.datetime.fromisoformat(str(start).replace("Z", "+00:00"))


def monatswerte(reihen: list[dict]) -> dict[tuple[int, int], float]:
    """Verbrauch je (Jahr, Monat) – bevorzugt 'change', sonst Differenz der Summen."""
    ergebnis: dict[tuple[int, int], float] = {}
    vorher = None
    for zeile in sorted(reihen, key=lambda z: z["start"]):
        d = als_datum(zeile["start"])
        schluessel = (d.year, d.month)
        if zeile.get("change") is not None:
            ergebnis[schluessel] = float(zeile["change"])
        elif zeile.get("sum") is not None:
            aktuell = float(zeile["sum"])
            if vorher is not None:
                ergebnis[schluessel] = aktuell - vorher
            vorher = aktuell
    return ergebnis


async def hauptprogramm(args) -> int:
    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=365 * args.jahre + 45)

    async with HaWs(args.url, args.token) as ha:
        rohdaten = await ha.befehl(
            type="recorder/statistics_during_period",
            start_time=start.isoformat(),
            statistic_ids=args.entities,
            period="month",
            types=["change", "sum"],
        )

        if not rohdaten:
            print("Keine Statistikdaten erhalten. Stimmen die Entity-IDs?", file=sys.stderr)
            return 1

        # Verbrauch aller Sensoren je Kalendermonat aufaddieren
        summe: dict[tuple[int, int], float] = defaultdict(float)
        for entity, reihen in rohdaten.items():
            werte = monatswerte(reihen)
            print(f"  {entity}: {len(werte)} Monate", file=sys.stderr)
            for schluessel, wert in werte.items():
                summe[schluessel] += max(0.0, wert)

        if not summe:
            print("Keine auswertbaren Monatswerte gefunden.", file=sys.stderr)
            return 1

        # laufenden Monat verwerfen, der ist noch unvollständig
        heute = dt.date.today()
        summe.pop((heute.year, heute.month), None)

        # je Kalendermonat über die letzten n Jahre mitteln (neueste zuerst)
        proMonat: dict[int, list[float]] = defaultdict(list)
        for (jahr, monat) in sorted(summe, reverse=True):
            if len(proMonat[monat]) < args.jahre:
                proMonat[monat].append(summe[(jahr, monat)])

        liter_je_m3 = args.liter_pro_m3
        mittel, zaehler = [], []
        print(f"\nMonatsverbrauch (gemittelt über max. {args.jahre} Jahr(e)):", file=sys.stderr)
        for monat in range(1, 13):
            werte = proMonat.get(monat, [])
            wert = round(sum(werte) / len(werte) * liter_je_m3, 1) if werte else 0.0
            mittel.append(wert)
            zaehler.append(len(werte))
            roh = ", ".join(f"{w * liter_je_m3:.0f}" for w in werte) or "keine Daten"
            print(f"  {MONATE[monat - 1]}  {wert:8.1f} L   (aus: {roh})", file=sys.stderr)

        fehlend = [MONATE[i] for i, z in enumerate(zaehler) if z == 0]
        summe_l = sum(mittel)
        print(f"\n  Jahresverbrauch: {summe_l:.0f} L "
              f"≈ {summe_l * args.kwh_pro_liter:.0f} kWh", file=sys.stderr)
        if fehlend:
            print(f"  ACHTUNG: keine Daten für {', '.join(fehlend)} – "
                  f"dort steht 0 L. Werte von Hand ergänzen!", file=sys.stderr)

        wert_mittel = ",".join(f"{w:g}" for w in mittel)
        wert_zaehler = ",".join(str(z) for z in zaehler)

        print("\ninput_text.gastank_monatsmittel_liter:", file=sys.stderr)
        print(wert_mittel)
        print("\ninput_text.gastank_monatszaehler:", file=sys.stderr)
        print(wert_zaehler)

        if len(wert_mittel) > 255:
            print("\nWARNUNG: Der Wert ist länger als 255 Zeichen und passt nicht "
                  "in den Helfer. Werte runden!", file=sys.stderr)

        if args.schreiben:
            for entity, wert in (
                ("input_text.gastank_monatsmittel_liter", wert_mittel),
                ("input_text.gastank_monatszaehler", wert_zaehler),
            ):
                await ha.befehl(
                    type="call_service", domain="input_text", service="set_value",
                    target={"entity_id": entity}, service_data={"value": wert},
                )
            print("\nIn Home Assistant geschrieben.", file=sys.stderr)

    return 0


def argumente():
    p = argparse.ArgumentParser(
        description="Monatsprofil für die Flüssiggas-Prognose aus der HA-Statistik berechnen.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--url", default="http://homeassistant.local:8123",
                   help="Basis-URL von Home Assistant")
    p.add_argument("--token", required=True,
                   help="Langlebiges Zugriffstoken (Profil → Sicherheit)")
    p.add_argument("--entities", nargs="+", required=True,
                   help="Verbrauchssensoren in m³, z. B. Heizung und Warmwasser")
    p.add_argument("--jahre", type=int, default=2,
                   help="Über wie viele Jahre je Kalendermonat gemittelt wird (Standard 2)")
    p.add_argument("--liter-pro-m3", type=float, default=3.92,
                   help="Umrechnung m³ Gas → Liter Flüssiggas (Standard 3.92)")
    p.add_argument("--kwh-pro-liter", type=float, default=7.0,
                   help="Energieinhalt je Liter, nur für die Ausgabe (Standard 7.0)")
    p.add_argument("--schreiben", action="store_true",
                   help="Ergebnis direkt in die input_text-Helfer schreiben")
    return p.parse_args()


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(hauptprogramm(argumente())))
    except KeyboardInterrupt:
        sys.exit(130)
    except RuntimeError as fehler:
        sys.exit(f"Fehler: {fehler}")
