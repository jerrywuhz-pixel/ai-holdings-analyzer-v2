"""
OpenClaw Gateway — FastAPI 入口

云端部署入口文件，组装所有 Gateway 组件：
- 微信小程序数据端点 (miniprogram router)
- 微信认证端点 (wechat_auth router)
- 心跳上报器 (HeartbeatReporter)
- Cron 端点 (Cloud Scheduler 触发)
- 健康检查 (Cloud Run 探针)
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from openclaw.gateway.heartbeat_reporter import HeartbeatReporter
from openclaw.gateway.middleware import GatewayDataMiddleware
from openclaw.gateway.routers import miniprogram, wechat_auth

logger = logging.getLogger(__name__)

# 哨兵初始化（可选）
try:
    from openclaw.gateway.sentry_service import init_sentry
    _HAS_SENTRY = True
except ImportError:
    _HAS_SENTRY = False

# 健康缓存（可选）
try:
    from openclaw.gateway.health_cache import HealthCache
    _HAS_HEALTH_CACHE = True
except ImportError:
    _HAS_HEALTH_CACHE = False


# ── 全局组件 ─────────────────────────────────────────────────

_heartbeat_reporter: HeartbeatReporter | None = None
_health_cache: HealthCache | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    global _heartbeat_reporter, _health_cache

    # Sentry
    if _HAS_SENTRY:
        init_sentry()

    # 健康缓存
    if _HAS_HEALTH_CACHE:
        _health_cache = HealthCache()

    # 初始化 GatewayDataMiddleware
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    skill_key = os.getenv("OPENCLAW_SKILL_KEY", supabase_key)

    if supabase_url and skill_key:
        middleware = GatewayDataMiddleware(
            skill_name="openclaw-gateway",
            api_key=skill_key,
            supabase_url=supabase_url,
        )
        app.state.gateway_middleware = middleware

        # Supabase 客户端 (供 wechat_auth 使用)
        try:
            from supabase import create_client
            app.state.supabase = create_client(supabase_url, supabase_key)
        except ImportError:
            app.state.supabase = None
    else:
        logger.warning("Supabase not configured, Gateway middleware disabled")
        app.state.gateway_middleware = None
        app.state.supabase = None

    # JWT Secret
    app.state.jwt_secret = os.getenv(
        "SUPABASE_JWT_SECRET", "dev-secret-change-in-production"
    )

    # 心跳上报
    _heartbeat_reporter = HeartbeatReporter()
    _heartbeat_reporter.register_skill("opportunity-hunter")
    _heartbeat_reporter.register_skill("position-aggregate")
    _heartbeat_reporter.register_skill("daily-analysis")
    _heartbeat_reporter.register_skill("quant-options-strategy")
    _heartbeat_reporter.start(interval_seconds=300)

    logger.info("OpenClaw Gateway started (mode=%s)", os.getenv("DEPLOYMENT_MODE", "local"))

    yield

    # 关闭
    if _heartbeat_reporter:
        _heartbeat_reporter.stop()
    logger.info("OpenClaw Gateway stopped")


app = FastAPI(
    title="OpenClaw Gateway",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
_cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
if _cors_origins:
    allow_origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]
else:
    allow_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Skill-Name"],
)

# 注册路由
app.include_router(wechat_auth.router)
app.include_router(miniprogram.router)


# ── 健康检查 ─────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Cloud Run 健康探针。"""
    gateway_status = {}
    if _health_cache:
        try:
            gateway_status = await _health_cache.get_gateway_status()
        except Exception:
            gateway_status = {"gateway": "unknown", "data_sources": []}

    return {
        "status": "ok",
        "version": "2.0.0",
        "service": "openclaw-gateway",
        "gateway": gateway_status.get("gateway", "unknown"),
        "data_sources": gateway_status.get("data_sources", []),
    }


@app.get("/")
def root():
    """根路径。"""
    return {
        "service": "OpenClaw Gateway",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
    }


# ── Cron 端点 (Cloud Scheduler 触发) ─────────────────────────

@app.post("/api/cron/daily-scan")
async def cron_daily_scan(request: Request):
    """
    Cron: 每日市场扫描 (Hermes 机会猎手)

    由 Cloud Scheduler 在工作日 15:30 CST 触发。
    使用 OIDC Token 验证调用者身份。
    """
    # 验证 OIDC Token (Cloud Scheduler 自带)
    _verify_cron_request(request)

    import importlib
    hermes_mod = importlib.import_module(
        "openclaw.skills.opportunity-hunter.hermes"
    )
    hermes = hermes_mod.HermesOrchestrator()
    reports = await hermes.generate_all_reports()

    return {
        "ok": True,
        "reports_generated": len([r for r in reports if r.get("ok")]),
        "total": len(reports),
    }


@app.post("/api/cron/sellput-score")
async def cron_sellput_score(request: Request):
    """
    Cron/API: Hermes Sell Put scoring.

    Body formats:
    - {"mode": "scan", "contracts": [...], "min_score": 70}
    - {"mode": "open", "contract": {...}}
    - {"mode": "hold", "position": {...}}
    Empty body returns a healthy no-candidate scan response.
    """
    _verify_cron_request(request)

    import importlib

    service_mod = importlib.import_module(
        "openclaw.skills.quant-options-strategy.hermes_sellput"
    )
    service = service_mod.HermesSellPutService()

    try:
        body = await request.json()
    except Exception:
        body = {}

    mode = body.get("mode", "scan")
    if mode == "open":
        return await service.evaluate_open_with_futu(body.get("contract", {}))
    if mode == "hold":
        return service.evaluate_hold(body.get("position", {}))

    return service.scan_candidates(
        body.get("contracts", []),
        min_score=int(body.get("min_score", 70)),
    )


@app.post("/api/cron/heartbeat")
async def cron_heartbeat(request: Request):
    """Cron: 心跳检测 (每 5 分钟)。"""
    _verify_cron_request(request)

    if _heartbeat_reporter:
        reported = await _heartbeat_reporter.report(gateway_status="healthy")
        stale_count = await _heartbeat_reporter.mark_stale_instances()
        return {"ok": True, "reported": reported, "stale_marked": stale_count}

    return {"ok": False, "message": "Heartbeat reporter not initialized"}


@app.post("/api/cron/stale-jobs")
async def cron_stale_jobs(request: Request):
    """Cron: 检查过期/超时任务 (每 10 分钟)。"""
    _verify_cron_request(request)

    try:
        from openclaw.gateway.job_manager import JobManager
        mgr = JobManager()

        stale_pending = await mgr.find_stale_pending_jobs()
        timed_out = await mgr.find_timed_out_running_jobs()

        handled = 0
        for job in timed_out:
            await mgr.timeout_job(job["id"])
            handled += 1

        return {
            "ok": True,
            "stale_pending": len(stale_pending),
            "timed_out_handled": handled,
        }
    except Exception as exc:
        logger.error("Stale jobs check failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _verify_cron_request(request: Request) -> None:
    """
    验证 Cron 请求来源。

    Cloud Scheduler 使用 OIDC Token，Header 中包含 Authorization: Bearer <token>。
    本地开发时可设置 OPENCLAW_CRON_SECRET 环境变量进行简单验证。
    """
    cron_secret = os.getenv("OPENCLAW_CRON_SECRET")
    if cron_secret:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Missing cron auth token")
        token = auth[7:]
        if token != cron_secret:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Invalid cron auth token")
