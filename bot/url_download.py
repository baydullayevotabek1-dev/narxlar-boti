"""Download Excel from URL (supports Google Drive share links, direct URLs)."""
import re
import urllib.parse
import aiohttp

MAX_URL_SIZE = 300 * 1024 * 1024  # 300 MB


def _gsheets_id(url: str) -> str | None:
    # https://docs.google.com/spreadsheets/d/FILE_ID/edit...
    m = re.search(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    return None


def _gdrive_id(url: str) -> str | None:
    # https://drive.google.com/file/d/FILE_ID/view?usp=sharing
    m = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    # https://drive.google.com/open?id=FILE_ID
    m = re.search(r"drive\.google\.com/(?:open|uc).*?[?&]id=([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    return None


def _normalize_url(url: str) -> str:
    # Google Sheets → xlsx export
    sid = _gsheets_id(url)
    if sid:
        return f"https://docs.google.com/spreadsheets/d/{sid}/export?format=xlsx"
    # Google Drive file → direct download
    fid = _gdrive_id(url)
    if fid:
        return f"https://drive.google.com/uc?export=download&id={fid}&confirm=t"
    return url


async def download_url(url: str) -> tuple[bytes, str]:
    """Return (file_bytes, filename)."""
    url = _normalize_url(url.strip())
    timeout = aiohttp.ClientTimeout(total=300)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, allow_redirects=True) as resp:
            resp.raise_for_status()
            content_length = int(resp.headers.get("Content-Length", 0))
            if content_length and content_length > MAX_URL_SIZE:
                raise ValueError(f"Fayl juda katta: {content_length/1024/1024:.1f} MB (max 300 MB)")

            # filename from headers — try filename*=UTF-8''... first, then filename="..."
            filename = "download.xlsx"
            cd = resp.headers.get("Content-Disposition", "")
            m = re.search(r"filename\*=UTF-8''([^;]+)", cd, re.IGNORECASE)
            if m:
                filename = urllib.parse.unquote(m.group(1).strip().strip('"'))
            else:
                m = re.search(r'filename="([^"]+)"', cd)
                if m:
                    filename = m.group(1)
                else:
                    m = re.search(r"filename=([^;]+)", cd)
                    if m:
                        filename = m.group(1).strip().strip('"')

            data = bytearray()
            async for chunk in resp.content.iter_chunked(64 * 1024):
                data.extend(chunk)
                if len(data) > MAX_URL_SIZE:
                    raise ValueError("Fayl 300 MB dan oshdi")
            return bytes(data), filename
