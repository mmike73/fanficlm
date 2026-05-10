from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import router
from app.services.lm_studio_client import LMClient

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.lm_client = LMClient()
    yield

app = FastAPI(title="LLM Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)