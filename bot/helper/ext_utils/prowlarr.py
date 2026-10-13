from os import getenv

from aiofiles import open as aiopen
from aiofiles.os import makedirs
from httpx import AsyncClient

# Search results from the Prowlarr plugin link to PROWLARR_URL without the API key.
# When such a link is sent to the bot, fetch it with the key and turn it into a
# magnet link or a local .torrent file that qBittorrent/aria2 can use.
PROWLARR_URL = getenv("PROWLARR_URL", "").rstrip("/")
PROWLARR_API_KEY = getenv("PROWLARR_API_KEY", "")


def is_prowlarr_link(link):
    return bool(PROWLARR_URL) and isinstance(link, str) and link.startswith(PROWLARR_URL)


async def resolve_prowlarr_link(link, dest_dir):
    async with AsyncClient(timeout=60, follow_redirects=False) as client:
        for _ in range(5):
            r = await client.get(
                link, headers={"X-Api-Key": PROWLARR_API_KEY, "User-Agent": "mltb"}
            )
            if r.is_redirect:
                link = r.headers["location"]
                if link.startswith("magnet:"):
                    return link
                continue
            r.raise_for_status()
            if not r.content.startswith(b"d"):
                raise ValueError("Prowlarr didn't return a torrent file")
            await makedirs(dest_dir, exist_ok=True)
            path = f"{dest_dir}/prowlarr.torrent"
            async with aiopen(path, "wb") as f:
                await f.write(r.content)
            return path
    raise ValueError("Too many redirects from Prowlarr")
