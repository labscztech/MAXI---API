from fastapi import FastAPI, Query, HTTPException, WebSocket, WebSocketDisconnect, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
import asyncio
from pathlib import Path

import database
import maxi_api

app = FastAPI(title="Maxi Portas - Dashboard")

# ── Auth dependencies ─────────────────────────────────────────────────────────
def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado")
    token = authorization.split(" ", 1)[1]
    user = database.get_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")
    return user


def admin_only(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Acesso negado — apenas administradores")
    return user


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


# ── Auth endpoints ────────────────────────────────────────────────────────────
class LoginBody(BaseModel):
    username: str
    password: str


@app.post("/api/login")
def login(body: LoginBody):
    user = database.authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")
    token = database.create_session(user["id"])
    return {"token": token, "role": user["role"], "username": user["username"], "id": user["id"]}


@app.post("/api/logout")
def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.lower().startswith("bearer "):
        database.delete_session(authorization.split(" ", 1)[1])
    return {"ok": True}


@app.get("/api/me")
def get_me(user: dict = Depends(get_current_user)):
    allowed = database.get_user_substatuses(user["id"])
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "allowed_substatus_ids": allowed if user["role"] == "USER" else None,
    }


class ChangePasswordBody(BaseModel):
    old_password: str
    new_password: str


@app.post("/api/change-password")
def change_password(body: ChangePasswordBody, user: dict = Depends(get_current_user)):
    ok = database.change_user_password(user["id"], body.old_password, body.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail="Senha atual incorreta")
    return {"ok": True}


# ── User management (admin only) ──────────────────────────────────────────────
@app.get("/api/users")
def list_users(_: dict = Depends(admin_only)):
    return database.get_all_users()


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "USER"
    substatus_ids: List[int] = []


@app.post("/api/users")
def create_user(body: UserCreate, _: dict = Depends(admin_only)):
    try:
        user_id = database.create_user(body.username, body.password, body.role)
    except Exception:
        raise HTTPException(status_code=409, detail="Nome de usuário já existe")
    if body.substatus_ids:
        database.set_user_substatuses(user_id, body.substatus_ids)
    return {"ok": True, "id": user_id}


class UserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    substatus_ids: Optional[List[int]] = None


@app.put("/api/users/{uid}")
def update_user(uid: int, body: UserUpdate, _: dict = Depends(admin_only)):
    database.update_user(uid, body.username, body.role, body.password)
    if body.substatus_ids is not None:
        database.set_user_substatuses(uid, body.substatus_ids)
    return {"ok": True}


@app.delete("/api/users/{uid}")
def delete_user(uid: int, current: dict = Depends(admin_only)):
    if uid == current["id"]:
        raise HTTPException(status_code=400, detail="Não é possível excluir sua própria conta")
    database.delete_user(uid)
    return {"ok": True}


# ── Orders ────────────────────────────────────────────────────────────────────
@app.get("/api/orders")
def list_orders(
    situacao:     Optional[str] = Query(None),
    substatus_id: Optional[int] = Query(None),
    parceiro:     Optional[str] = Query(None),
    regiao:       Optional[str] = Query(None),
    search:       Optional[str] = Query(None),
    _: dict = Depends(get_current_user),
):
    return database.get_orders(
        situacao=situacao,
        substatus_id=substatus_id,
        parceiro=parceiro,
        regiao=regiao,
        search=search,
    )


@app.get("/api/orders/{op}")
def get_order(op: str, _: dict = Depends(get_current_user)):
    order = database.get_order_by_op(op)
    if not order:
        raise HTTPException(status_code=404, detail="OP não encontrada")
    return order


class SubstatusUpdate(BaseModel):
    substatus_id: Optional[int] = None
    scanner_input: str = ""


@app.put("/api/orders/{op}/substatus")
async def update_substatus(op: str, body: SubstatusUpdate, user: dict = Depends(get_current_user)):
    # Operadores só podem aplicar substatuses autorizados
    if user["role"] == "USER" and body.substatus_id is not None:
        allowed = database.get_user_substatuses(user["id"])
        if body.substatus_id not in allowed:
            raise HTTPException(status_code=403, detail="Sub-status não autorizado para este operador")

    ok = database.update_substatus(op, body.substatus_id, body.scanner_input)
    if not ok:
        raise HTTPException(status_code=404, detail="OP não encontrada")

    order = database.get_order_by_op(op)
    await manager.broadcast({"event": "substatus_updated", "order": order})
    return order


# ── Sub-statuses ──────────────────────────────────────────────────────────────
@app.get("/api/substatuses")
def list_substatuses(_: dict = Depends(get_current_user)):
    return database.get_substatuses()


class SubstatusUpsert(BaseModel):
    id: int
    fluxo: Optional[str] = "Geral"
    nome: str
    cor: str = "#64748b"
    ordem: int


@app.put("/api/substatuses")
def upsert_substatus(body: SubstatusUpsert, _: dict = Depends(admin_only)):
    database.upsert_substatus(body.id, body.nome, body.cor, body.ordem, body.fluxo)
    return {"ok": True}


# ── Stats ─────────────────────────────────────────────────────────────────────
@app.get("/api/stats")
def get_stats(_: dict = Depends(admin_only)):
    return database.get_stats()


# ── Filtros disponíveis ───────────────────────────────────────────────────────
@app.get("/api/filters")
def get_filters(_: dict = Depends(get_current_user)):
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
def get_history(op: Optional[str] = Query(None), limit: int = Query(50), _: dict = Depends(admin_only)):
    return database.get_history(op=op, limit=limit)


# ── Sync ──────────────────────────────────────────────────────────────────────
@app.post("/api/sync")
async def sync_data(_: dict = Depends(admin_only)):
    api_token, empresa = maxi_api.get_api_config()

    if api_token and empresa:
        try:
            records = await asyncio.get_event_loop().run_in_executor(
                None, maxi_api.sync_last_90_days_orders, api_token, empresa
            )
            count = database.upsert_orders_list(records)
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e))
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


# ── Configuração da API ───────────────────────────────────────────────────────
class ApiConfig(BaseModel):
    token: str
    empresa: str


@app.post("/api/api-config")
def save_api_config(body: ApiConfig, _: dict = Depends(admin_only)):
    maxi_api.save_api_config(body.token, body.empresa)
    return {"ok": True}


@app.get("/api/api-config")
def get_api_config_status(_: dict = Depends(admin_only)):
    api_token, empresa = maxi_api.get_api_config()
    return {"configured": bool(api_token and empresa), "empresa": empresa}


# ── Busca de OP via API ───────────────────────────────────────────────────────
@app.get("/api/fetch-op/{op}")
async def fetch_op_from_api(op: str, _: dict = Depends(get_current_user)):
    try:
        record = await asyncio.get_event_loop().run_in_executor(
            None, maxi_api.fetch_order_from_api, op
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    if not record:
        raise HTTPException(status_code=404, detail=f"OP {op} não encontrada na API.")

    database.upsert_single_order(record)
    return database.get_order_by_op(op)


# ── Barcode lookup ────────────────────────────────────────────────────────────
@app.get("/api/scan/{code}")
async def scan_barcode(code: str, _: dict = Depends(get_current_user)):
    op = code.strip().replace("\n", "").replace("\r", "")

    api_ok = False
    try:
        api_token, empresa = maxi_api.get_api_config()
        if api_token and empresa:
            record = await asyncio.get_event_loop().run_in_executor(
                None, maxi_api.fetch_order_from_api, op, api_token, empresa
            )
            if record:
                database.upsert_single_order(record)
                api_ok = True
    except Exception:
        pass

    order = database.get_order_by_op(op)
    if not order:
        orders = database.get_orders(search=op)
        if orders:
            return {"found": True, "exact": False, "order": orders[0], "alternatives": orders[:5], "api_synced": api_ok}
        return {"found": False, "op": op, "api_synced": api_ok}
    return {"found": True, "exact": True, "order": order, "api_synced": api_ok}


# ── Static files ──────────────────────────────────────────────────────────────
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def serve_frontend():
    return FileResponse(str(static_dir / "index.html"))


@app.get("/login")
def serve_login():
    return FileResponse(str(static_dir / "login.html"))


@app.get("/scanner")
def serve_scanner():
    return FileResponse(str(static_dir / "scanner.html"))
