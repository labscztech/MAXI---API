from fastapi import FastAPI, Query, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import asyncio
from pathlib import Path

import database
import scraper

app = FastAPI(title="Maxi Portas - Dashboard")

# ── Startup ──────────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    database.init_db()


# ── WebSocket manager (live updates) ─────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()   # keep alive / ping
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ── Orders ────────────────────────────────────────────────────────────────────
@app.get("/api/orders")
def list_orders(
    situacao:    Optional[str] = Query(None),
    substatus_id: Optional[int] = Query(None),
    parceiro:    Optional[str] = Query(None),
    regiao:      Optional[str] = Query(None),
    search:      Optional[str] = Query(None),
):
    orders = database.get_orders(
        situacao=situacao,
        substatus_id=substatus_id,
        parceiro=parceiro,
        regiao=regiao,
        search=search,
    )
    return orders


@app.get("/api/orders/{op}")
def get_order(op: str):
    order = database.get_order_by_op(op)
    if not order:
        raise HTTPException(status_code=404, detail="OP não encontrada")
    return order


class SubstatusUpdate(BaseModel):
    substatus_id: Optional[int] = None
    scanner_input: str = ""


@app.put("/api/orders/{op}/substatus")
async def update_substatus(op: str, body: SubstatusUpdate):
    ok = database.update_substatus(op, body.substatus_id, body.scanner_input)
    if not ok:
        raise HTTPException(status_code=404, detail="OP não encontrada")

    order = database.get_order_by_op(op)
    # Broadcast to all connected dashboards
    await manager.broadcast({"event": "substatus_updated", "order": order})
    return order


# ── Sub-statuses ──────────────────────────────────────────────────────────────
@app.get("/api/substatuses")
def list_substatuses():
    return database.get_substatuses()


class SubstatusUpsert(BaseModel):
    id: int
    nome: str
    cor: str = "#64748b"
    ordem: int


@app.put("/api/substatuses")
def upsert_substatus(body: SubstatusUpsert):
    database.upsert_substatus(body.id, body.nome, body.cor, body.ordem)
    return {"ok": True}


# ── Stats ─────────────────────────────────────────────────────────────────────
@app.get("/api/stats")
def get_stats():
    return database.get_stats()


# ── Filtros disponíveis ───────────────────────────────────────────────────────
@app.get("/api/filters")
def get_filters():
    with database.get_conn() as conn:
        parceiros = [r[0] for r in conn.execute(
            "SELECT DISTINCT parceiro FROM orders WHERE parceiro != '' ORDER BY parceiro"
        ).fetchall()]
        regioes = [r[0] for r in conn.execute(
            "SELECT DISTINCT regiao FROM orders WHERE regiao != '' ORDER BY regiao"
        ).fetchall()]
        situacoes = [r[0] for r in conn.execute(
            "SELECT DISTINCT situacao FROM orders WHERE situacao != '' ORDER BY situacao"
        ).fetchall()]
    return {"parceiros": parceiros, "regioes": regioes, "situacoes": situacoes}


# ── Histórico ─────────────────────────────────────────────────────────────────
@app.get("/api/history")
def get_history(op: Optional[str] = Query(None), limit: int = Query(50)):
    return database.get_history(op=op, limit=limit)


# ── Credenciais ───────────────────────────────────────────────────────────────
class Credentials(BaseModel):
    usuario: str
    senha: str


@app.post("/api/credentials")
def save_credentials(body: Credentials):
    scraper.save_config({"usuario": body.usuario, "senha": body.senha})
    return {"ok": True}


@app.get("/api/credentials")
def get_credentials_status():
    usuario, _ = scraper.get_credentials()
    return {"configured": bool(usuario), "usuario": usuario}


# ── Sync ──────────────────────────────────────────────────────────────────────
@app.post("/api/sync")
async def sync_data():
    """
    Faz login automático com as credenciais salvas,
    detecta o total de registros e importa tudo de uma vez.
    Sem credenciais → reimporta output.html local.
    """
    usuario, senha = scraper.get_credentials()

    if usuario and senha:
        try:
            html_all, found = await asyncio.get_event_loop().run_in_executor(
                None, scraper.fetch_all_records, usuario, senha
            )
            count = database.load_from_html(html_all)
        except RuntimeError as e:
            raise HTTPException(status_code=401, detail=str(e))
    else:
        html_path = Path(__file__).parent.parent / "output.html"
        if html_path.exists():
            html_all = html_path.read_text(encoding="utf-8", errors="replace")
            count = database.load_from_html(html_all)
        else:
            count = database.load_pedidos_json()

    stats = database.get_stats()
    await manager.broadcast({"event": "sync_done", "count": count})
    return {"imported": count, "stats": stats}


# ── Barcode lookup ────────────────────────────────────────────────────────────
@app.get("/api/scan/{code}")
def scan_barcode(code: str):
    """Recebe leitura do scanner e retorna o pedido correspondente."""
    # Remove espaços/quebras vindos do scanner
    op = code.strip().replace("\n", "").replace("\r", "")
    order = database.get_order_by_op(op)
    if not order:
        # Tenta busca parcial
        orders = database.get_orders(search=op)
        if orders:
            return {"found": True, "exact": False, "order": orders[0], "alternatives": orders[:5]}
        return {"found": False, "op": op}
    return {"found": True, "exact": True, "order": order}


# ── Static files ──────────────────────────────────────────────────────────────
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def serve_frontend():
    return FileResponse(str(static_dir / "index.html"))
