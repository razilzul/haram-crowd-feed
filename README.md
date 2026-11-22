# Haram crowd feed

A GitHub Actions job watches the Saudi Quran TV live camera of Masjid al-Haram. Whenever the
camera shows the wide view of the Kaaba it saves the picture and measures how much of the
mataf floor around the Kaaba is covered by people (`analyze.py`: plain pixel rules, no AI service).

Output, on the `feed` branch (rewritten in place):

- `kaaba.jpg`: the latest Kaaba view
- `latest.json`: `{"at", "crowd" (0-1), "level", "video", "camera_at"}` (unix seconds)
- `log.json`: `[[unix seconds, crowd], ...]` for the last 14 days

Read by the Umrah Companion app's Crowds tab. Runs only until 7 Dec 2026 (`STOP_AFTER` in feed.py).

Why thumbnails, not video: YouTube asks cloud servers to sign in before streaming video, but the
live thumbnail (`maxresdefault_live.jpg`) stays open. It updates about every 5 minutes, so the job
checks once a minute.
