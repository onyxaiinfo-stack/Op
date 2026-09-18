import time
import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from checkout_engine import check_card

START_TIME = time.time()
stats = {
    "total": 0,
    "approved": 0,
    "charged": 0,
    "declined": 0,
    "error": 0,
    "last_10": []
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/health")
async def health():
    uptime = int(time.time() - START_TIME)
    m, s = divmod(uptime, 60)
    return {
        "status": "ok",
        "uptime": f"{m}m {s}s",
        "total_checks": stats["total"]
    }

@app.get("/check")
async def check(cc: str, site: str, proxy: str = None):
    start = time.time()
    try:
        result = await check_card(cc, site, proxy)
    except Exception as e:
        result = {
            "status": "Error",
            "message": str(e),
            "gateway": "-",
            "price": "-"
        }

    elapsed = round(time.time() - start, 2)
    result["time"] = f"{elapsed}s"

    stats["total"] += 1
    status = result["status"].lower()
    if status == "approved":
        stats["approved"] += 1
    elif status == "charged":
        stats["charged"] += 1
    elif status == "declined":
        stats["declined"] += 1
    else:
        stats["error"] += 1

    entry = {
        "cc": cc[:4] + "xxxxxxxx" + cc.split("|")[0][-4:],
        "site": site,
        "gateway": result.get("gateway", "-"),
        "status": result["status"],
        "message": result.get("message", "-"),
        "time": result["time"]
    }
    stats["last_10"].insert(0, entry)
    stats["last_10"] = stats["last_10"][:10]

    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=5001, reload=False)