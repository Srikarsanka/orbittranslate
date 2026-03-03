from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import router as voice_translation_router

app = FastAPI(title="Voice Translation Service", version="1.0.0")

# Configure CORS for standalone service
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voice_translation_router, prefix="/api/voice-translation")

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Voice Translation"}
