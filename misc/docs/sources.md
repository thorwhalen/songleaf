# Sources: decisions and survey

This is the running decision record for where `songleaf` gets lyrics, chords and score snippets from. The full source-by-source survey (licence, ToS, verdict) is posted at [songleaf#3](https://github.com/thorwhalen/songleaf/issues/3#issuecomment-5679072923). This file adds the two decisions that needed the repo owner: the "Tabs" app ([#5](https://github.com/thorwhalen/songleaf/issues/5)) and MuseScore ([#6](https://github.com/thorwhalen/songleaf/issues/6)).

## Ultimate Guitar (songleaf#5)

The "Tabs" app is **Ultimate Guitar**.

Ultimate Guitar has no public API and its terms of service explicitly bar automated scraping — that route stays closed (per the songleaf#3 survey). What a paying subscriber *can* do legitimately, through the official website UI (not the mobile app), is:

- **Download** a Pro tab as a Guitar Pro file (`.gp`/`.gpx`) — website only, not offered on official (non-Pro) tabs.
- **Download or print a PDF** of a tab via the site's own "Download PDF" / print button.
- **Export all of one's own personal tabs** in bulk, from the Personal Tabs page.

There is no legitimate way to automate any of this — it is a logged-in, per-song, human action on ultimate-guitar.com. The route that respects that: the subscriber downloads the files they want (Guitar Pro or PDF) through the website as usual, and drops them into a local folder that `songleaf` indexes, the same pattern `scoreseek.sources.LocalFolderSource` already uses for offline score files.

**Decision:** no automated Ultimate Guitar source. Track ingestion of user-exported Guitar Pro/PDF files as a normal local-folder source in [songleaf#16](https://github.com/thorwhalen/songleaf/issues/16).

## Ultimate Guitar community charts (songleaf#28)

Correction to the section above: UG's terms of service (as updated 2026-08-24) have no explicit scraping clause. What they do say, and what songleaf's design follows:

- Use is personal and non-commercial; printing text tabs and lyrics is allowed.
- No reproduction of content onto memory or devices, and no circumventing content protection (section 6.2, section 6.4). Official and Pro tabs live in UG's own player behind the subscription: songleaf refuses them on every route (`songleaf.ultimate_guitar.refusal`, the bookmarklet, `/import`).
- Others may link to UG but not replicate it (section 14). songleaf keeps the chart for the one reader who imported it, with `provenance.license = "personal"` and the page URL as provenance.
- UG scores page requests for bots, so no route here makes requests on anyone's behalf from the server.

The routes, in the order songleaf prefers them:

1. **Paste** (the default): copy the chart from the page and paste it into "Paste a song". No contact with UG.
2. **Bookmarklet**: "Send to songleaf", offered under "Paste a song". Run in the reader's own browser on a community "Chords" or "Tabs" page they opened, it reads the chart from that page (`.js-store`, `page.data.tab_view.wiki_tab.content`, plus tonality and capo) and opens songleaf's paste form filled in with it, through the URL fragment (never seen by a server). Nothing is stored until the reader presses Import. Official and Pro pages get an explanation instead.
3. **`UltimateGuitarURLSource`** / `songleaf import-url <url>`: local command line only, off unless `SONGLEAF_UG_URL=1`, one URL per call, cached as `ug:<id>` (a stored chart is not fetched again), never searches, never in `default_sources()`, never behind an HTTP route, so never in the deployed app.

Charts from a UG URL, by any route, are stored as `ug:<id>`.

## MuseScore (songleaf#6)

A MuseScore developer API key pair could not be obtained (musescore.com's developer API requires emailing `api@musescore.com` to request one, and that request did not resolve — see songleaf#6).

Without an API key, the same shape of answer applies as for Ultimate Guitar. musescore.com lets a Pro subscriber **export their own or subscription-unlocked scores** through the website (or desktop app) as MusicXML, MSCZ, MIDI, PDF, MP3 or PNG — a per-score, logged-in, human action, not an automatable one without the key `songleaf` doesn't have.

Two routes stay open without any account at all, and are already how `scoreseek` reaches scores:
- **OpenScore Lieder** (~1,356 art songs, CC0) and **IMSLP** (public-domain classical) — both already wired into `scoreseek`.
- **PDMX** (250K public-domain MusicXML corpus, local bulk download) — also already in `scoreseek`.

**Decision:** no automated MuseScore.com source (blocked on the API key). Score snippets come from `scoreseek`'s existing open sources by default. MuseScore Pro exports, like Ultimate Guitar's, are ingested as local files the same way — tracked in [songleaf#16](https://github.com/thorwhalen/songleaf/issues/16) alongside the Ultimate Guitar case, since both are "drop an exported file in a folder" the same mechanism.

## Local-folder ingestion (songleaf#16)

Built: `songleaf.sources.LocalFolderSource` indexes `~/.local/share/songleaf/imports/` (or any folder you point it at). Text exports are parsed as chords-over-lyrics charts; Guitar Pro/MusicXML/MSCZ/MIDI/PDF exports become a score-linked `Song` with no lyrics text. It reads only what's already on disk — no network calls, no login.

## What's built vs. what's a source survey

The verdicts in songleaf#3 that don't need the user (Kaggle corpus, Chordonomicon, LRCLIB, music21 corpus, McGill Billboard, ChoCo, and `scoreseek`'s existing sources) stand as written there. This file only adds the two decisions that came back from the owner.
