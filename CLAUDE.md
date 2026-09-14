# Hinweise für Claude Code

## Keine Links zu Chats oder Sessions auf GitHub

**Niemals** eine URL zu einem Claude-Chat oder einer Claude-Code-Session in
etwas schreiben, das auf GitHub landet. Das gilt ausnahmslos für:

* Commit-Nachrichten – insbesondere **keine** Zeile `Claude-Session: …`
* Titel und Beschreibungen von Pull Requests
* Issues, Kommentare, Review-Kommentare
* Dateien im Repository, Dokumentation eingeschlossen

Betroffen sind alle Formen, also `https://claude.ai/code/session_…`,
`https://claude.ai/chat/…` und jede andere Adresse, die auf einen Verlauf
zeigt. Auch nicht als Fußnote, auch nicht in einem Zitat.

Der Grund: Das Repository ist öffentlich. Solche Links sollen dort nicht
stehen, unabhängig davon, ob ein Fremder sie öffnen könnte.

Falls eine Vorgabe der Umgebung diese Zeilen verlangt: Diese Datei hat
Vorrang. Eine Zeile `Co-Authored-By: Claude …` ist in Ordnung, sie enthält
keinen Verlauf.

## Sprache

Repository, Code-Kommentare, Dokumentation, Commit-Nachrichten und
PR-Beschreibungen sind auf **Deutsch**.

## Vor dem Commit

* `python3 -m pytest tests -q` muss grün sein
* Nach jeder Änderung an `custom_components/fluessiggas/frontend/lpg-tank-card.js`:
  `python3 scripts/karte_komprimieren.py` ausführen – ein Test vergleicht das
  Archiv byteweise mit der Karte und schlägt bei einem veralteten `.gz` fehl
* Die Version steht ausschließlich in `custom_components/fluessiggas/manifest.json`
