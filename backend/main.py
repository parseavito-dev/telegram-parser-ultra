import os
import uvicorn
import json
import asyncio
from fastapi import FastAPI, WebSocket, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from backend.parser import parser

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")), name="static")

@app.get("/")
async def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.post("/api/parse")
async def start_parse(request: Request):
    data = await request.json()
    target = data.get("target", "").strip()
    if not target:
        return JSONResponse({"error": "Укажи ссылку"}, status_code=400)

    task_id = await parser.start_parsing(
        session_name="my_account",
        target=target,
        limit=int(data.get("limit", 0)),
        online_only=data.get("online_only", False),
        recent_days=int(data.get("recent_days", 0)),
        letter=data.get("letter", "")[:1].lower(),
        use_proxy=data.get("use_proxy", False),
        proxy=data.get("proxy")
    )
    return {"task_id": task_id}

@app.post("/api/stop/{task_id}")
async def stop_parse(task_id: str):
    parser.stop_task(task_id)
    return {"status": "stopped"}

@app.get("/api/download/{task_id}")
async def download(task_id: str, format: str = "csv"):
    file_path = parser.get_result_file(task_id, format)
    if file_path and os.path.exists(file_path):
        return FileResponse(file_path, filename=f"users_{task_id}.{format}")
    return JSONResponse({"error": "Файл ещё не готов"}, status_code=404)

@app.websocket("/ws/{task_id}")
async def ws(websocket: WebSocket, task_id: str):
    await websocket.accept()
    queue = None
    for _ in range(30):
        queue = parser.get_log_queue(task_id)
        if queue: break
        await asyncio.sleep(0.5)
    if not queue:
        await websocket.close()
        return

    try:
        while True:
            msg = await asyncio.wait_for(queue.get(), timeout=30)
            await websocket.send_text(json.dumps(msg))
            if msg.get("type") in ["finished", "stopped"]:
                break
    except:
        pass
    finally:
        await websocket.close()

if __name__ == "__main__":
    os.makedirs("backend/results", exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=8000)