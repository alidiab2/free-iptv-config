# Free IPTV — online config

The app downloads `config.json` from https://github.com/alidiab2/free-iptv-config on every launch.

- `message`: plain text shown on the activation screen (optional).
- `secret`: encrypted activation code + account list. Only the app can read it.

To change it: edit `config.private.json` (never upload this one), run `npm run config:encrypt`,
then upload the new `config.json` to the repo. Devices pick it up within ~5 minutes.

## Programme guide

`.github/workflows/epg.yml` runs `epg/build.py` twice a day and force-pushes `epg.json` to the `epg` branch; the app reads it from there. Nothing to do by hand. When the provider's channel line-up changes a lot, run `python3 scripts/epg-channels.py` in the app repo and push the new `epg/channels.txt`.
