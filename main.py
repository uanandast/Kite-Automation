# pyrefly: ignore [missing-import]
from fastapi import FastAPI

app = FastAPI(title="Kite API Migration", description="Migrated FastAPI for Kite App")

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Hello from Kite FastAPI in Docker!"}

if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
