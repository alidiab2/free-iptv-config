# Free IPTV — online config

The app downloads `config.json` from https://github.com/alidiab2/free-iptv-config on every launch.

- `message`: plain text shown on the activation screen (optional).
- `secret`: encrypted activation code + account list. Only the app can read it.

To change it: edit `config.private.json` (never upload this one), run `npm run config:encrypt`,
then upload the new `config.json` to the repo. Devices pick it up within ~5 minutes.
