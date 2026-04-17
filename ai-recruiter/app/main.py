"""
AI Recruiter by AI Octopus
WhatsApp-native hiring platform for Kuwait.
"""
from fastapi import FastAPI

from app.routers import webhook, internal
from app.database import engine, Base

# Create all tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Recruiter",
    description="WhatsApp-native hiring platform by AI Octopus",
    version="0.1.0",
)

# Mount routers
app.include_router(webhook.router)
app.include_router(internal.router)


@app.get("/")
def root():
    return {
        "name": "AI Recruiter by AI Octopus",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
