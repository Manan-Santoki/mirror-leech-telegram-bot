# VERSION: 1.0
# AUTHORS: mltb fork
# qBittorrent search plugin that searches every indexer configured in Prowlarr.
# Reads PROWLARR_URL and PROWLARR_API_KEY from the environment. The API key is never
# put in result links: non-magnet links point at PROWLARR_URL without the key, and the
# bot adds the key as a header when it downloads them.

import json
import os
from datetime import datetime
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from urllib.request import Request, urlopen

from novaprinter import prettyPrinter

PROWLARR_URL = os.environ.get("PROWLARR_URL", "http://127.0.0.1:9696").rstrip("/")
PROWLARR_API_KEY = os.environ.get("PROWLARR_API_KEY", "")


def _strip_key(url):
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k.lower() != "apikey"]
    base = urlsplit(PROWLARR_URL)
    return urlunsplit((base.scheme, base.netloc, parts.path, urlencode(query), ""))


class prowlarr(object):
    url = PROWLARR_URL
    name = "Prowlarr"
    supported_categories = {
        "all": None,
        "anime": [5070],
        "books": [7000, 8000],
        "games": [1000, 4050],
        "movies": [2000],
        "music": [3000],
        "software": [4000],
        "tv": [5000],
    }

    def search(self, what, cat="all"):
        # qBittorrent may route every socket through its SOCKS proxy; Prowlarr is
        # reached directly (PROWLARR_URL is internal), so turn that off here
        try:
            from helpers import enable_socks_proxy

            enable_socks_proxy(False)
        except Exception:
            pass
        params = [("query", what.replace("%20", " ")), ("type", "search")]
        for c in self.supported_categories.get(cat) or []:
            params.append(("categories", c))
        req = Request(
            f"{PROWLARR_URL}/api/v1/search?{urlencode(params)}",
            headers={"X-Api-Key": PROWLARR_API_KEY, "User-Agent": "mltb-prowlarr"},
        )
        try:
            with urlopen(req, timeout=90) as resp:
                results = json.load(resp)
        except Exception:
            return
        for r in results:
            link = r.get("magnetUrl") or r.get("downloadUrl")
            if not link:
                continue
            if not link.startswith("magnet:"):
                link = _strip_key(link)
            try:
                pub_date = int(datetime.fromisoformat(r["publishDate"].replace("Z", "+00:00")).timestamp())
            except Exception:
                pub_date = -1
            prettyPrinter(
                {
                    "link": link,
                    "name": f"[{r.get('indexer', '')}] {r.get('title', '')}",
                    "size": str(r.get("size", -1)),
                    "seeds": r.get("seeders", -1),
                    "leech": r.get("leechers", -1),
                    "engine_url": self.url,
                    "desc_link": r.get("infoUrl") or r.get("guid") or self.url,
                    "pub_date": pub_date,
                }
            )

    def download_torrent(self, info):
        print(info + " " + info)
