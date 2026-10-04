#!/usr/bin/env python3
"""Builds epg.json: a small programme guide for the app from free XMLTV feeds.

Runs on GitHub Actions (.github/workflows/epg.yml) twice a day; devices download the result
from raw.githubusercontent.com. Channels are keyed by a normalised name (same rules as the
app's `epgKey` in src/epgOnline.ts), so the provider's channel list isn't needed here.
aliases.json maps our channel names that differ from the feeds' names; channels.txt is the
provider's channel names in that form (scripts/epg-channels.py in the app repo writes it).
"""
import gzip, io, json, re, sys, time, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

# First source with real data for a channel wins: Arabic titles first, then the wide English feed.
# Feeds carry hundreds of channels we don't have, so each is cut down to channels.txt.
SOURCES = [
    ('https://www.open-epg.com/files/saudiarabia1.xml', None),
    ('https://www.open-epg.com/files/morocco1.xml', None),
    ('https://www.open-epg.com/files/qatar1.xml', None),
    ('https://epgshare01.online/epgshare01/epg_ripper_AE1.xml.gz', 'https://www.open-epg.com/files/uae1.xml'),
    ('https://www.open-epg.com/files/egypt2.xml', None),
    ('https://www.open-epg.com/files/uae3.xml', None),
    ('https://www.open-epg.com/files/palestine1.xml', None),
]
EPGPW = 'https://epg.pw/xmltv/epg.xml.gz'  # huge; only the channel ids listed in aliases.json
PAST, AHEAD = 1 * 3600, 36 * 3600
DESC = 120


def key(s: str) -> str:
    """Keep in sync with epgKey() in the app."""
    s = s.lower().replace('ᴴᴰ', ' hd ')
    s = re.sub(r'^\s*[a-z]{2}\s*[:|]\s*', '', s)
    s = re.sub(r'\.[a-z]{2,4}$', '', s)
    s = re.sub(r'[^a-z0-9\u0600-\u06ff]+', ' ', s)
    s = re.sub(r'\b(hd|fhd|uhd|sd|4k|8k|hevc|ultra|live|tv|channel|ch|mono|digital|plus|new|the|backup|vip|raw|h265|1080p?|720p?)\b', ' ', s, flags=re.A)
    s = re.sub(r'\b(al|el) ', 'al', s, flags=re.A)
    return re.sub(r'\s+', '', s)


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 FreeIPTV-EPG'})
    data = urllib.request.urlopen(req, timeout=300).read()
    if data[:2] == b'\x1f\x8b':
        data = gzip.decompress(data)
    return data


def ts(s):
    return int(datetime.strptime(s[:20].strip(), '%Y%m%d%H%M%S %z').timestamp())


def parse(data, only=None):
    """{channel id: (names, [programmes])} for programmes inside the window."""
    now = time.time()
    chans, progs = {}, {}
    for _, el in ET.iterparse(io.BytesIO(data)):
        if el.tag == 'channel':
            cid = el.get('id')
            if only is None or cid in only:
                chans[cid] = [cid] + [d.text for d in el.findall('display-name') if d.text]
            el.clear()
        elif el.tag == 'programme':
            cid = el.get('channel')
            if only is None or cid in only:
                try:
                    a, b = ts(el.get('start', '')), ts(el.get('stop', ''))
                except ValueError:
                    a = b = 0
                if b > now - PAST and a < now + AHEAD and b > a:
                    title = (el.findtext('title') or '').strip()
                    desc = re.sub(r'\s+', ' ', el.findtext('desc') or '').strip()[:DESC]
                    if title:
                        progs.setdefault(cid, []).append((a, b, title, desc))
            el.clear()
    return {cid: (chans.get(cid, [cid]), sorted(p)) for cid, p in progs.items()}


def real(names, progs):
    """Skips placeholder guides (one repeated title, or the channel's own name)."""
    titles = {p[2] for p in progs}
    if len(titles) <= 1:
        return False
    own = {key(n) for n in names}
    return sum(key(p[2]) in own for p in progs) < len(progs) / 2


def main(out_path, aliases_path, channels_path):
    aliases = json.load(open(aliases_path, encoding='utf-8'))
    try:
        ours = set(open(channels_path, encoding='utf-8').read().split()) | set(aliases.get('names', {}).values())
    except OSError:
        ours = None
    guide, origin = {}, {}
    now = time.time()

    def add(src, parsed):
        n = 0
        for cid, (names, progs) in parsed.items():
            if not real(names, progs) or not any(a <= now < b for a, b, *_ in progs):
                continue
            for name in names:
                k = key(name)
                if ours is not None and k not in ours:
                    continue
                if len(k) >= 2 and k not in guide:
                    guide[k] = progs
                    origin[k] = src
                    n += 1
        print(f'{src}: {len(parsed)} channels, {n} new keys', file=sys.stderr)

    for url, backup in SOURCES:
        for u in [url] + ([backup] if backup else []):
            try:
                add(u.rsplit('/', 1)[-1], parse(fetch(u)))
                break
            except Exception as e:  # one dead feed mustn't sink the rest
                print(f'{u}: {e}', file=sys.stderr)
    ids = aliases.get('epgpw', {})
    if ids:
        try:
            parsed = parse(fetch(EPGPW), set(ids.values()))
            add('epg.pw', {cid: ([k for k, v in ids.items() if v == cid], p) for cid, (_, p) in parsed.items()})
        except Exception as e:
            print(f'epg.pw: {e}', file=sys.stderr)

    if len(set(map(id, guide.values()))) < 100:
        sys.exit(f'only {len(guide)} channels; keeping the previous epg.json')

    # Same programme list under several keys: store it once.
    base = int(now // 3600 * 3600)
    lists, index, seen = [], {}, {}
    for k, progs in guide.items():
        sig = id(progs)
        if sig not in seen:
            seen[sig] = len(lists)
            rows = []
            for a, b, title, desc in progs:
                row = [(a - base) // 60, (b - a) // 60, title]
                if desc and desc != title:
                    row.append(desc)
                rows.append(row)
            lists.append(rows)
        index[k] = seen[sig]
    for ours, theirs in aliases.get('names', {}).items():
        if theirs in index and ours not in index:
            index[ours] = index[theirs]
    doc = {'v': 1, 'base': base, 'built': int(now), 'keys': index, 'lists': lists}
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, separators=(',', ':'))
    print(f'{len(index)} keys, {len(lists)} channels', file=sys.stderr)


if __name__ == '__main__':
    out, aliases, channels = (sys.argv[1:] + ['epg.json', 'epg/aliases.json', 'epg/channels.txt'][len(sys.argv) - 1:])[:3]
    main(out, aliases, channels)
