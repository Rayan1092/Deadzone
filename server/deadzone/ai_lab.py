"""Opt-in serving of versioned ML evidence, separate from live Command data."""
import os
from pathlib import PurePath

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class AILabAssets(StaticFiles):
    extensions = {".json", ".png", ".jpg", ".jpeg", ".webp", ".svg"}

    async def get_response(self, path, scope):
        if os.environ.get("DZ_AI_LAB") != "1":
            raise HTTPException(404)
        if scope["method"] not in {"GET", "HEAD"}:
            raise HTTPException(405)
        asset = PurePath(path)
        if (asset.suffix.lower() not in self.extensions
                or any(part.startswith(".") for part in asset.parts)):
            raise HTTPException(404)
        # StaticFiles resolves real paths inside its root (follow_symlink=False).
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response
