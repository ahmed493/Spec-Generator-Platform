"""
Spec Generator Platform - Main Entry Point
FastAPI application for generating specifications from data sources
"""
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
"""from app.auth_sso import get_current_user, require_role"""
from app.config.settings import settings
from app.db import init_db

app = FastAPI(
    title="Spec Generator",
    description="Platform for generating technical and functional specifications from data sources",
    version="0.1.0"
)

# Create tables at startup
@app.on_event("startup")
def on_startup():
    init_db()

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include API routes
app.include_router(router, prefix="/api")

"""
# --- SSO Auth Example Endpoints ---
# @app.get("/auth/protected")
# def protected_route(user=Depends(get_current_user)):
#     return {"user": user}
#
# @app.get("/auth/admin")
# def admin_route(user=Depends(require_role("Admin"))):
#     return {"admin": user}
"""


@app.get("/")
async def root():
    return {
        "message": "Spec Generator API",
        "docs": "/docs",
        "llm_provider": settings.llm_provider
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
