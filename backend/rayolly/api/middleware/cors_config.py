"""CORS configuration -- restrict origins in production."""
DEVELOPMENT_ORIGINS = ["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"]

def get_cors_origins(env: str = "development") -> list[str]:
    if env == "production":
        return []  # Set via RAYOLLY_CORS_ORIGINS env var
    return ["*"]  # Allow all in development
