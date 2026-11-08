"""Production files: immutable Vite hashes, revalidated entry points."""
import re

from fastapi.staticfiles import StaticFiles

HASHED_ASSET = re.compile(r"^assets/[^/]+-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9]+$")


class ProductionFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304):
            if HASHED_ASSET.fullmatch(path.replace("\\", "/").lstrip("/")):
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            elif response.headers.get("content-type", "").startswith("text/html"):
                response.headers["Cache-Control"] = "no-cache"
        return response
