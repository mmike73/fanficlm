import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import router
from app.services.lm_studio_client import LMClient
from app.services.theme_detector import ThemeDetector

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.lm_client = LMClient()
    app.state.theme_detector = ThemeDetector()
    yield

app = FastAPI(title="LLM Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)