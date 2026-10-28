from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .api import (assistant, auth, billing, client, commercial, dashboard, documents, drydock, finance, fleet, fleetops, insurance, ops,
                  ports, positions, security, supply)
from .db import migrate


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate()
    yield


app = FastAPI(title="MARIS: offshore fleet ERP for SEAMEC", lifespan=lifespan,
              description="Fleet, contracts, daily reports, billing, maintenance, crew, tenders, supply, port calls, dry docks, insurance and finance. "
                          "All data is representative.")
for module in (auth, fleet, ops, billing, dashboard, assistant, positions, fleetops, client, commercial, documents, supply, ports, drydock,
               insurance, finance, security):
    app.include_router(module.router)
app.include_router(auth.users)


# In production the built web app is served from here too, so the whole tool is one process.
if config.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"))

    DIST = config.FRONTEND_DIST.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def web_app(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        # Files at the top of the build (sw.js, icons) are served as themselves; every other path is the app.
        file = (DIST / path).resolve()
        if path and file.is_file() and file.is_relative_to(DIST):
            # The service worker must be re-checked on every load, or vessels keep an old app.
            return FileResponse(file, headers={"Cache-Control": "no-cache"} if path == "sw.js" else None)
        return FileResponse(DIST / "index.html")
