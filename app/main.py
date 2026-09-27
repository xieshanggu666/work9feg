import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import Base, engine
from app.models import *  # noqa: F401,F403 确保模型注册

from app.api import auth, users, questions, exams, attempts, grades, bookings

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    data_dir = BASE_DIR / "data"
    os.makedirs(data_dir, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

# 开发阶段前端 Vite dev server 跨域访问（支持端口被占用后自动切换）
_frontend_port = os.getenv("FRONTEND_PORT", "")
_cors_frontend_origins = (
    [f"http://127.0.0.1:{_frontend_port}", f"http://localhost:{_frontend_port}"]
    if _frontend_port
    else ["http://127.0.0.1:5173", "http://localhost:5173"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(users.router, prefix=settings.API_PREFIX)
app.include_router(questions.router, prefix=settings.API_PREFIX)
app.include_router(exams.router, prefix=settings.API_PREFIX)
app.include_router(attempts.router, prefix=settings.API_PREFIX)
app.include_router(grades.router, prefix=settings.API_PREFIX)
app.include_router(bookings.router, prefix=settings.API_PREFIX)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


# ---------- 生产环境：托管前端构建产物（SPA） ----------
if FRONTEND_DIST.exists():
    # 静态资源目录（js / css / 图标等）
    app.mount(
        "/assets",
        StaticFiles(directory=str(FRONTEND_DIST / "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_entry(full_path: str):
        """所有非 API 路径统一回退到 index.html，由前端路由处理。"""
        # API / 文档路径不回退到前端，返回标准 404（JSON）
        if full_path.startswith(("api/", "docs", "redoc", "openapi.json")):
            raise HTTPException(status_code=404, detail="Not Found")
        target = FRONTEND_DIST / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
