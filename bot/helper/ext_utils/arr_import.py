from asyncio import sleep
from os import getenv
from os import path as ospath, walk

from aiofiles.os import path as aiopath
from httpx import AsyncClient

from ... import LOGGER
from .bot_utils import cmd_exec

# Uploads whose rclone destination is under ARR_REMOTE ("arr:" by default) are handed
# to Radarr (movies/) or Sonarr (tv/), which rename and move them into their library.
ARR_REMOTE = getenv("ARR_REMOTE", "arr")
ARR_LOCAL_DIR = getenv("ARR_LOCAL_DIR", "/arr-import").rstrip("/")
ARR_REMOTE_DIR = getenv("ARR_REMOTE_DIR", "/downloads/mltb").rstrip("/")
RADARR_URL = getenv("RADARR_URL", "").rstrip("/")
RADARR_API_KEY = getenv("RADARR_API_KEY", "")
SONARR_URL = getenv("SONARR_URL", "").rstrip("/")
SONARR_API_KEY = getenv("SONARR_API_KEY", "")
ARR_QUALITY_PROFILE = getenv("ARR_QUALITY_PROFILE", "Any")


VIDEO_EXTENSIONS = (".mkv", ".mp4", ".avi", ".m4v", ".mov", ".ts", ".wmv", ".webm")


async def _remaining_videos(local_path):
    if not await aiopath.exists(local_path):
        return 0
    if await aiopath.isfile(local_path):
        return int(local_path.lower().endswith(VIDEO_EXTENSIONS))
    count = 0
    for _, _, files in walk(local_path):
        count += sum(f.lower().endswith(VIDEO_EXTENSIONS) for f in files)
    return count


def is_arr_destination(rclone_path):
    return bool(rclone_path) and rclone_path.startswith(f"{ARR_REMOTE}:")


class _Arr:
    def __init__(self, url, api_key):
        self.url = url
        self.headers = {"X-Api-Key": api_key, "User-Agent": "mltb-arr-import/1.0"}

    async def get(self, client, endpoint, **params):
        r = await client.get(
            f"{self.url}/api/v3/{endpoint}", headers=self.headers, params=params
        )
        r.raise_for_status()
        return r.json()

    async def post(self, client, endpoint, data):
        r = await client.post(
            f"{self.url}/api/v3/{endpoint}", headers=self.headers, json=data
        )
        r.raise_for_status()
        return r.json()

    async def defaults(self, client):
        profiles = await self.get(client, "qualityprofile")
        profile = next(
            (p for p in profiles if p["name"] == ARR_QUALITY_PROFILE), profiles[0]
        )
        root = (await self.get(client, "rootfolder"))[0]["path"]
        return profile["id"], root

    async def wait_command(self, client, command_id, timeout=600):
        for _ in range(timeout // 5):
            await sleep(5)
            cmd = await self.get(client, f"command/{command_id}")
            if cmd["status"] in ("completed", "failed", "aborted", "cancelled"):
                return cmd["status"]
        return "timeout"


async def _import_movie(client, arr, name, remote_path):
    parsed = await arr.get(client, "parse", title=name)
    movie = parsed.get("movie")
    if not movie:
        info = parsed.get("parsedMovieInfo") or {}
        title = (info.get("movieTitles") or [info.get("movieTitle") or name])[0]
        year = info.get("year") or 0
        term = f"{title} {year}" if year else title
        results = await arr.get(client, "movie/lookup", term=term)
        if not results:
            return f"Radarr couldn't identify <code>{title}</code>"
        movie = next((m for m in results if year and m.get("year") == year), results[0])
        if not movie.get("id"):
            profile_id, root = await arr.defaults(client)
            movie.update(
                qualityProfileId=profile_id,
                rootFolderPath=root,
                monitored=False,
                minimumAvailability="released",
                addOptions={"searchForMovie": False},
            )
            movie = await arr.post(client, "movie", movie)
            LOGGER.info(f"Added to Radarr: {movie['title']} ({movie['year']})")
    cmd = await arr.post(
        client,
        "command",
        {"name": "DownloadedMoviesScan", "path": remote_path, "importMode": "Move"},
    )
    return f"{movie['title']} ({movie['year']})", cmd["id"]


async def _import_series(client, arr, name, remote_path):
    parsed = await arr.get(client, "parse", title=name)
    series = parsed.get("series")
    if not series:
        info = parsed.get("parsedEpisodeInfo") or {}
        title = info.get("seriesTitle") or name
        results = await arr.get(client, "series/lookup", term=title)
        if not results:
            return f"Sonarr couldn't identify <code>{title}</code>"
        series = results[0]
        if not series.get("id"):
            profile_id, root = await arr.defaults(client)
            series.update(
                qualityProfileId=profile_id,
                rootFolderPath=root,
                monitored=False,
                seasonFolder=True,
                addOptions={
                    "monitor": "none",
                    "searchForMissingEpisodes": False,
                    "searchForCutoffUnmetEpisodes": False,
                },
            )
            series = await arr.post(client, "series", series)
            LOGGER.info(f"Added to Sonarr: {series['title']}")
    cmd = await arr.post(
        client,
        "command",
        {"name": "DownloadedEpisodesScan", "path": remote_path, "importMode": "Move"},
    )
    return series["title"], cmd["id"]


async def arr_import(rclone_path, name):
    """Hand a finished upload to Radarr/Sonarr. Returns a status line for the user."""
    rel = rclone_path.split(":", 1)[1].lstrip("/")
    local_rel = rel.removeprefix(ARR_LOCAL_DIR.lstrip("/")).lstrip("/")
    kind = local_rel.split("/", 1)[0]
    local_path = f"{ARR_LOCAL_DIR}/{local_rel}"
    remote_path = f"{ARR_REMOTE_DIR}/{local_rel}"

    if kind == "movies":
        arr, label, importer = _Arr(RADARR_URL, RADARR_API_KEY), "Radarr", _import_movie
    elif kind == "tv":
        arr, label, importer = _Arr(SONARR_URL, SONARR_API_KEY), "Sonarr", _import_series
    else:
        return f"Unknown import folder <code>{kind}</code>, expected movies or tv"
    if not arr.url or not arr.headers["X-Api-Key"]:
        return f"{label} is not configured, files left in <code>{remote_path}</code>"

    # Radarr/Sonarr run as a different user and must be able to move these files
    await cmd_exec(["chmod", "a+rwx", ARR_LOCAL_DIR, f"{ARR_LOCAL_DIR}/{kind}"])
    await cmd_exec(["chmod", "-R", "a+rwX", local_path])
    try:
        async with AsyncClient(timeout=60) as client:
            result = await importer(client, arr, name, remote_path)
            if isinstance(result, str):
                return f"{result}, files left in <code>{remote_path}</code>"
            title, command_id = result
            status = await arr.wait_command(client, command_id)
    except Exception as e:
        LOGGER.error(f"{label} import failed for {name}: {e}")
        return f"{label} import failed: {e}"

    if status == "completed" and not await _remaining_videos(local_path):
        return f"Imported to {label} as <b>{title}</b>"
    return (
        f"{label} matched <b>{title}</b> but didn't import everything ({status}). "
        f"Check {label} > Wanted > Manual Import for <code>{ospath.basename(remote_path)}</code>"
    )
