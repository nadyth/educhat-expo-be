from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import auth, ollama, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="Edu Chat BE", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(ollama.router, prefix="/ollama", tags=["ollama"])


def _start_tunnel(port: int):
    import shutil
    import subprocess
    import sys

    if not shutil.which("cloudflared"):
        print("cloudflared not found. Install it: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")
        sys.exit(1)

    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # cloudflared prints the public URL to stderr/stdout; wait for it
    for line in proc.stdout:
        line = line.decode(errors="replace").strip()
        if line:
            print(f"[tunnel] {line}")
        if "https://" in line and ".trycloudflare.com" in line:
            break

    return proc


def run():
    import uvicorn

    from app.config import settings

    port = 8000

    if settings.tunnel:
        proc = _start_tunnel(port)
        try:
            uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
        finally:
            proc.terminate()
            proc.wait()
    else:
        uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)