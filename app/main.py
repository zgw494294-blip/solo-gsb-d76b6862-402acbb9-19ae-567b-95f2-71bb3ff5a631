"""步道坡线规划台 —— FastAPI 入口。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .planner import PlanError, plan_trail

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="步道坡线规划台", version="1.0.0")


def _error(message: str, status: int = 422) -> JSONResponse:
    return JSONResponse(status_code=status, content={"feasible": False, "reason": message})


@app.exception_handler(PlanError)
async def plan_error_handler(_request: Request, exc: PlanError) -> JSONResponse:
    return _error(str(exc))


@app.post("/api/plan")
async def api_plan(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        return _error("请求体必须是合法的 JSON。", status=400)
    if not isinstance(payload, dict) or "ground" not in payload:
        return _error("请求 JSON 必须包含 ground 字段（地面标高数组）。", status=400)

    try:
        result = plan_trail(payload["ground"])
    except PlanError as exc:
        return _error(str(exc))
    return JSONResponse(status_code=200, content=result)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
