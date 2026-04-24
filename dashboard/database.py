import sqlite3
import json
import re
import html as html_mod
import hashlib
import secrets
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "maxi.db"
DATA_PATH = Path(__file__).parent.parent / "pedidos.json"

DEFAULT_SUBSTATUSES = [
    # PROD. PERFIL
    {"id": 1, "fluxo": "PROD. PERFIL", "nome": "1 - CORTE", "cor": "#f59e0b", "ordem": 1},
    {"id": 2, "fluxo": "PROD. PERFIL", "nome": "2 - USINAGEM", "cor": "#f97316", "ordem": 2},
    {"id": 3, "fluxo": "PROD. PERFIL", "nome": "3 - AGUARDANDO VIDRO", "cor": "#94a3b8", "ordem": 3},
    {"id": 4, "fluxo": "PROD. PERFIL", "nome": "4 - MONTAGEM", "cor": "#8b5cf6", "ordem": 4},
    {"id": 5, "fluxo": "PROD. PERFIL", "nome": "5 - QUALIDADE", "cor": "#10b981", "ordem": 5},
    {"id": 6, "fluxo": "PROD. PERFIL", "nome": "6 - EMBALAGEM", "cor": "#84cc16", "ordem": 6},
    {"id": 7, "fluxo": "PROD. PERFIL", "nome": "7 - EXPEDIÇÃO", "cor": "#22c55e", "ordem": 7},

    # PROD. VIDRO (FLUXO SIMPLES)
    {"id": 8, "fluxo": "PROD. VIDRO (FLUXO SIMPLES)", "nome": "1 - CORTE", "cor": "#f59e0b", "ordem": 8},
    {"id": 9, "fluxo": "PROD. VIDRO (FLUXO SIMPLES)", "nome": "2 - LAPIDAÇÃO", "cor": "#0ea5e9", "ordem": 9},
    {"id": 10, "fluxo": "PROD. VIDRO (FLUXO SIMPLES)", "nome": "3 - LAVAGEM", "cor": "#3b82f6", "ordem": 10},
    {"id": 11, "fluxo": "PROD. VIDRO (FLUXO SIMPLES)", "nome": "4 - QUALIDADE", "cor": "#10b981", "ordem": 11},
    {"id": 12, "fluxo": "PROD. VIDRO (FLUXO SIMPLES)", "nome": "5 - EMBALAGEM", "cor": "#84cc16", "ordem": 12},
    {"id": 13, "fluxo": "PROD. VIDRO (FLUXO SIMPLES)", "nome": "6 - EXPEDIÇÃO", "cor": "#22c55e", "ordem": 13},

    # PROD. VIDRO (FLUXO COMPLEXO)
    {"id": 14, "fluxo": "PROD. VIDRO (FLUXO COMPLEXO)", "nome": "1 - CORTE", "cor": "#f59e0b", "ordem": 14},
    {"id": 15, "fluxo": "PROD. VIDRO (FLUXO COMPLEXO)", "nome": "2 - LAPIDAÇÃO", "cor": "#0ea5e9", "ordem": 15},
    {"id": 16, "fluxo": "PROD. VIDRO (FLUXO COMPLEXO)", "nome": "3.1 - BISOTÊ", "cor": "#6366f1", "ordem": 16},
    {"id": 17, "fluxo": "PROD. VIDRO (FLUXO COMPLEXO)", "nome": "3.2 - PINTURA", "cor": "#d946ef", "ordem": 17},
    {"id": 18, "fluxo": "PROD. VIDRO (FLUXO COMPLEXO)", "nome": "3.3 - JATO", "cor": "#8b5cf6", "ordem": 18},
    {"id": 19, "fluxo": "PROD. VIDRO (FLUXO COMPLEXO)", "nome": "3.4 - RECORTE/MODELAGEM", "cor": "#ec4899", "ordem": 19},
    {"id": 20, "fluxo": "PROD. VIDRO (FLUXO COMPLEXO)", "nome": "4 - LAVAGEM", "cor": "#3b82f6", "ordem": 20},
    {"id": 21, "fluxo": "PROD. VIDRO (FLUXO COMPLEXO)", "nome": "5 - MONTAGEM", "cor": "#a855f7", "ordem": 21},
    {"id": 22, "fluxo": "PROD. VIDRO (FLUXO COMPLEXO)", "nome": "6 - QUALIDADE", "cor": "#10b981", "ordem": 22},
    {"id": 23, "fluxo": "PROD. VIDRO (FLUXO COMPLEXO)", "nome": "7 - EMBALAGEM", "cor": "#84cc16", "ordem": 23},
    {"id": 24, "fluxo": "PROD. VIDRO (FLUXO COMPLEXO)", "nome": "8 - EXPEDIÇÃO", "cor": "#22c55e", "ordem": 24},
]


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS orders (
                op              TEXT PRIMARY KEY,
                parceiro        TEXT,
                razao_social    TEXT,
                fantasia        TEXT,
                nome_consumidor TEXT,
                situacao        TEXT,
                substatus_id    INTEGER,
                data_orcamento  TEXT,
                data_pedido     TEXT,
                ultima_alteracao TEXT,
                qtd_portas      INTEGER DEFAULT 0,
                qtd_vidros      INTEGER DEFAULT 0,
                qtd_quadros     INTEGER DEFAULT 0,
                qtd_camarim     INTEGER DEFAULT 0,
                qtd_estrutural  INTEGER DEFAULT 0,
                qtd_total       INTEGER DEFAULT 0,
                valor_total     TEXT,
                vendedor_pedido TEXT,
                andamento       TEXT,
                regiao          TEXT,
                pedido_fabrica  TEXT,
                pedido_parceiro TEXT,
                aprov_cliente   TEXT,
                aprov_filial    TEXT,
                aprov_empresa   TEXT,
                substatus_updated_at TEXT,
                raw_json        TEXT,
                cliente_cnpj_cpf TEXT,
                cliente_fone    TEXT,
                cliente_email   TEXT,
                cliente_cidade  TEXT,
                cliente_uf      TEXT,
                previsao_entrega TEXT,
                data_producao   TEXT,
                data_produzido  TEXT,
                data_entregue_parceiro TEXT,
                data_entregue_cliente  TEXT
            );

            CREATE TABLE IF NOT EXISTS substatuses (
                id      INTEGER PRIMARY KEY,
                fluxo   TEXT NOT NULL DEFAULT 'Geral',
                nome    TEXT NOT NULL,
                cor     TEXT NOT NULL DEFAULT '#64748b',
                ordem   INTEGER NOT NULL,
                ativo   INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS substatus_history (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                op                  TEXT NOT NULL,
                substatus_anterior  TEXT,
                substatus_novo      TEXT,
                atualizado_em       TEXT DEFAULT (datetime('now','localtime')),
                scanner_input       TEXT
            );
        """)

        # Database Fluxos Migration
        sub_cols = {r[1] for r in conn.execute("PRAGMA table_info(substatuses)").fetchall()}
        if "fluxo" not in sub_cols:
            conn.execute("ALTER TABLE substatuses ADD COLUMN fluxo TEXT DEFAULT 'Geral'")
            # Wipe all previous un-grouped sub-statuses as they are incompatible
            conn.execute("DELETE FROM substatuses")
            # Clear invalid references from all orders
            conn.execute("UPDATE orders SET substatus_id = NULL")

        # Seed sub-statuses only if empty
        count = conn.execute("SELECT COUNT(*) FROM substatuses").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO substatuses (id, fluxo, nome, cor, ordem) VALUES (:id, :fluxo, :nome, :cor, :ordem)",
                DEFAULT_SUBSTATUSES
            )

        # Auth tables
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS auth_users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt          TEXT NOT NULL,
                role          TEXT NOT NULL DEFAULT 'USER',
                created_at    TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token      TEXT PRIMARY KEY,
                user_id    INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (user_id) REFERENCES auth_users(id)
            );
            CREATE TABLE IF NOT EXISTS user_substatuses (
                user_id      INTEGER NOT NULL,
                substatus_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, substatus_id),
                FOREIGN KEY (user_id) REFERENCES auth_users(id),
                FOREIGN KEY (substatus_id) REFERENCES substatuses(id)
            );
        """)

        # First-boot: cria admin padrão se não existir nenhum
        if conn.execute("SELECT COUNT(*) FROM auth_users WHERE role='ADMIN'").fetchone()[0] == 0:
            pwd_hash, salt = _hash_password('admin')
            conn.execute(
                "INSERT INTO auth_users (username, password_hash, salt, role) VALUES (?,?,?,'ADMIN')",
                ('admin', pwd_hash, salt)
            )

        # Migração: adicionar colunas novas em bancos existentes
        existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(orders)").fetchall()}
        new_cols = [
            "cliente_cnpj_cpf", "cliente_fone", "cliente_email",
            "cliente_cidade", "cliente_uf", "previsao_entrega",
            "data_producao", "data_produzido",
            "data_entregue_parceiro", "data_entregue_cliente",
        ]
        for col in new_cols:
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE orders ADD COLUMN {col} TEXT")

    load_pedidos_json()


def load_pedidos_json():
    if not DATA_PATH.exists():
        return 0

    with open(DATA_PATH, encoding="utf-8") as f:
        records = json.load(f)

    def to_int(v):
        try:
            return int(str(v).replace(".", "").replace(",", ""))
        except Exception:
            return 0

    rows = []
    for r in records:
        rows.append({
            "op":               r.get("OP", ""),
            "parceiro":         r.get("Parceiro", ""),
            "razao_social":     r.get("Razao Social", ""),
            "fantasia":         r.get("Fantasia", ""),
            "nome_consumidor":  r.get("Nome Consumidor", ""),
            "situacao":         r.get("Situacao", ""),
            "substatus_id":     None,
            "data_orcamento":   r.get("Data Orcamento", ""),
            "data_pedido":      r.get("Data Pedido", ""),
            "ultima_alteracao": r.get("Ultima Alteracao", ""),
            "qtd_portas":       to_int(r.get("Qtd Portas", 0)),
            "qtd_vidros":       to_int(r.get("Qtd Vidros", 0)),
            "qtd_quadros":      to_int(r.get("Qtd Quadros", 0)),
            "qtd_camarim":      to_int(r.get("Qtd Camarim", 0)),
            "qtd_estrutural":   to_int(r.get("Qtd Estrutural", 0)),
            "qtd_total":        to_int(r.get("Qtd Total", 0)),
            "valor_total":      r.get("Valor Total", ""),
            "vendedor_pedido":  r.get("Vendedor Pedido", ""),
            "andamento":        r.get("Andamento", ""),
            "regiao":           r.get("Regiao", ""),
            "pedido_fabrica":   r.get("Pedido Fabrica", ""),
            "pedido_parceiro":  r.get("Pedido Parceiro", ""),
            "aprov_cliente":    r.get("Aprov Cliente", ""),
            "aprov_filial":     r.get("Aprov Filial", ""),
            "aprov_empresa":    r.get("Aprov Empresa", ""),
            "substatus_updated_at": None,
            "raw_json":         json.dumps(r, ensure_ascii=False),
        })

    with get_conn() as conn:
        conn.executemany("""
            INSERT INTO orders (
                op, parceiro, razao_social, fantasia, nome_consumidor, situacao,
                substatus_id, data_orcamento, data_pedido, ultima_alteracao,
                qtd_portas, qtd_vidros, qtd_quadros, qtd_camarim, qtd_estrutural,
                qtd_total, valor_total, vendedor_pedido, andamento, regiao,
                pedido_fabrica, pedido_parceiro, aprov_cliente, aprov_filial,
                aprov_empresa, substatus_updated_at, raw_json
            ) VALUES (
                :op, :parceiro, :razao_social, :fantasia, :nome_consumidor, :situacao,
                :substatus_id, :data_orcamento, :data_pedido, :ultima_alteracao,
                :qtd_portas, :qtd_vidros, :qtd_quadros, :qtd_camarim, :qtd_estrutural,
                :qtd_total, :valor_total, :vendedor_pedido, :andamento, :regiao,
                :pedido_fabrica, :pedido_parceiro, :aprov_cliente, :aprov_filial,
                :aprov_empresa, :substatus_updated_at, :raw_json
            ) ON CONFLICT(op) DO UPDATE SET
                parceiro        = excluded.parceiro,
                razao_social    = excluded.razao_social,
                fantasia        = excluded.fantasia,
                nome_consumidor = excluded.nome_consumidor,
                situacao        = excluded.situacao,
                data_orcamento  = excluded.data_orcamento,
                data_pedido     = excluded.data_pedido,
                ultima_alteracao= excluded.ultima_alteracao,
                qtd_portas      = excluded.qtd_portas,
                qtd_vidros      = excluded.qtd_vidros,
                qtd_quadros     = excluded.qtd_quadros,
                qtd_camarim     = excluded.qtd_camarim,
                qtd_estrutural  = excluded.qtd_estrutural,
                qtd_total       = excluded.qtd_total,
                valor_total     = excluded.valor_total,
                vendedor_pedido = excluded.vendedor_pedido,
                andamento       = excluded.andamento,
                regiao          = excluded.regiao,
                pedido_fabrica  = excluded.pedido_fabrica,
                pedido_parceiro = excluded.pedido_parceiro,
                aprov_cliente   = excluded.aprov_cliente,
                aprov_filial    = excluded.aprov_filial,
                aprov_empresa   = excluded.aprov_empresa,
                raw_json        = excluded.raw_json
        """, rows)

    return len(rows)


def upsert_single_order(record: dict):
    """Insere ou atualiza um único pedido vindo da API.
    Preserva substatus_id já existente."""
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO orders (
                op, parceiro, razao_social, fantasia, nome_consumidor, situacao,
                data_orcamento, data_pedido, ultima_alteracao,
                qtd_portas, qtd_vidros, qtd_quadros, qtd_camarim, qtd_estrutural,
                qtd_total, valor_total, vendedor_pedido, andamento, regiao,
                pedido_fabrica, pedido_parceiro, aprov_cliente, aprov_filial,
                aprov_empresa, raw_json,
                cliente_cnpj_cpf, cliente_fone, cliente_email, cliente_cidade, cliente_uf,
                previsao_entrega, data_producao, data_produzido,
                data_entregue_parceiro, data_entregue_cliente
            ) VALUES (
                :op, :parceiro, :razao_social, :fantasia, :nome_consumidor, :situacao,
                :data_orcamento, :data_pedido, :ultima_alteracao,
                :qtd_portas, :qtd_vidros, :qtd_quadros, :qtd_camarim, :qtd_estrutural,
                :qtd_total, :valor_total, :vendedor_pedido, :andamento, :regiao,
                :pedido_fabrica, :pedido_parceiro, :aprov_cliente, :aprov_filial,
                :aprov_empresa, :raw_json,
                :cliente_cnpj_cpf, :cliente_fone, :cliente_email, :cliente_cidade, :cliente_uf,
                :previsao_entrega, :data_producao, :data_produzido,
                :data_entregue_parceiro, :data_entregue_cliente
            ) ON CONFLICT(op) DO UPDATE SET
                parceiro        = excluded.parceiro,
                razao_social    = excluded.razao_social,
                fantasia        = excluded.fantasia,
                nome_consumidor = excluded.nome_consumidor,
                situacao        = excluded.situacao,
                data_orcamento  = excluded.data_orcamento,
                data_pedido     = excluded.data_pedido,
                ultima_alteracao= excluded.ultima_alteracao,
                qtd_portas      = excluded.qtd_portas,
                qtd_vidros      = excluded.qtd_vidros,
                qtd_quadros     = excluded.qtd_quadros,
                qtd_camarim     = excluded.qtd_camarim,
                qtd_estrutural  = excluded.qtd_estrutural,
                qtd_total       = excluded.qtd_total,
                valor_total     = excluded.valor_total,
                vendedor_pedido = excluded.vendedor_pedido,
                andamento       = excluded.andamento,
                regiao          = excluded.regiao,
                pedido_fabrica  = excluded.pedido_fabrica,
                pedido_parceiro = excluded.pedido_parceiro,
                aprov_cliente   = excluded.aprov_cliente,
                aprov_filial    = excluded.aprov_filial,
                aprov_empresa   = excluded.aprov_empresa,
                raw_json        = excluded.raw_json,
                cliente_cnpj_cpf = excluded.cliente_cnpj_cpf,
                cliente_fone    = excluded.cliente_fone,
                cliente_email   = excluded.cliente_email,
                cliente_cidade  = excluded.cliente_cidade,
                cliente_uf      = excluded.cliente_uf,
                previsao_entrega = excluded.previsao_entrega,
                data_producao   = excluded.data_producao,
                data_produzido  = excluded.data_produzido,
                data_entregue_parceiro = excluded.data_entregue_parceiro,
                data_entregue_cliente  = excluded.data_entregue_cliente
                -- substatus_id intencionalmente NÃO atualizado para preservar atualizações manuais
        """, record)
    return True


def upsert_orders_list(records: list[dict]):
    """Insere ou atualiza ordens vindas da API de lista.
    Atualiza apenas informações básicas (status, valor, datas), e
    NÃO zera as quantidades que só vêm na API de pedido completo."""
    if not records:
        return 0

    with get_conn() as conn:
        conn.executemany("""
            INSERT INTO orders (
                op, parceiro, razao_social, situacao,
                data_orcamento, ultima_alteracao,
                valor_total, andamento, cliente_cnpj_cpf,
                -- campos que a API da lista não traz mas precisam de valor inicial
                fantasia, nome_consumidor, data_pedido,
                qtd_portas, qtd_vidros, qtd_quadros, qtd_camarim, qtd_estrutural, qtd_total,
                vendedor_pedido, regiao, pedido_fabrica, pedido_parceiro,
                aprov_cliente, aprov_filial, aprov_empresa, raw_json
            ) VALUES (
                :op, :parceiro, :razao_social, :situacao,
                :data_orcamento, :ultima_alteracao,
                :valor_total, :andamento, :cliente_cnpj_cpf,
                '', '', '',
                0, 0, 0, 0, 0, 0,
                '', '', '', '',
                '', '', '', :raw_json
            ) ON CONFLICT(op) DO UPDATE SET
                parceiro        = excluded.parceiro,
                razao_social    = excluded.razao_social,
                situacao        = excluded.situacao,
                -- para evitar sobrescrever a data original das outras APIs com a da listagem, deixamos como está
                data_orcamento  = coalesce(nullif(orders.data_orcamento, ''), excluded.data_orcamento),
                ultima_alteracao= excluded.ultima_alteracao,
                valor_total     = excluded.valor_total,
                andamento       = excluded.andamento,
                cliente_cnpj_cpf= excluded.cliente_cnpj_cpf
                -- NOTE: quantidades, vendedor e outras aprovações NÃO são mexidas.
                -- raw_json a gente só atualiza da listagem se estiver vazio ou mantemos o do pedido para não perder ITENS
        """, records)
    return len(records)


def get_orders(situacao=None, substatus_id=None, parceiro=None, regiao=None, search=None):
    sql = """
        SELECT o.*, s.nome as substatus_nome, s.cor as substatus_cor
        FROM orders o
        LEFT JOIN substatuses s ON o.substatus_id = s.id
        WHERE 1=1
    """
    params = []

    if situacao and situacao != "TODOS":
        sql += " AND o.situacao = ?"
        params.append(situacao)

    if substatus_id is not None:
        if substatus_id == 0:
            sql += " AND o.substatus_id IS NULL"
        else:
            sql += " AND o.substatus_id = ?"
            params.append(substatus_id)

    if parceiro:
        sql += " AND o.parceiro = ?"
        params.append(parceiro)

    if regiao:
        sql += " AND o.regiao = ?"
        params.append(regiao)

    if search:
        sql += " AND (o.op LIKE ? OR o.razao_social LIKE ? OR o.fantasia LIKE ? OR o.nome_consumidor LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like, like])

    sql += " ORDER BY o.op DESC"

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def get_order_by_op(op: str):
    with get_conn() as conn:
        row = conn.execute("""
            SELECT o.*, s.nome as substatus_nome, s.cor as substatus_cor
            FROM orders o
            LEFT JOIN substatuses s ON o.substatus_id = s.id
            WHERE o.op = ?
        """, (op,)).fetchone()
        return dict(row) if row else None


def update_substatus(op: str, substatus_id: int | None, scanner_input: str = ""):
    with get_conn() as conn:
        current = conn.execute("SELECT substatus_id FROM orders WHERE op = ?", (op,)).fetchone()
        if not current:
            return False

        sub_anterior = None
        sub_novo = None

        if current["substatus_id"] is not None:
            row = conn.execute("SELECT nome FROM substatuses WHERE id = ?", (current["substatus_id"],)).fetchone()
            sub_anterior = row["nome"] if row else None

        if substatus_id is not None:
            row = conn.execute("SELECT nome FROM substatuses WHERE id = ?", (substatus_id,)).fetchone()
            sub_novo = row["nome"] if row else None

        conn.execute(
            "UPDATE orders SET substatus_id = ?, substatus_updated_at = datetime('now','localtime') WHERE op = ?",
            (substatus_id, op)
        )
        conn.execute("""
            INSERT INTO substatus_history (op, substatus_anterior, substatus_novo, scanner_input)
            VALUES (?, ?, ?, ?)
        """, (op, sub_anterior, sub_novo, scanner_input))

    return True


def get_substatuses():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM substatuses WHERE ativo = 1 ORDER BY ordem").fetchall()
        return [dict(r) for r in rows]


def upsert_substatus(id: int, nome: str, cor: str, ordem: int, fluxo: str = 'Geral'):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO substatuses (id, fluxo, nome, cor, ordem)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET nome=excluded.nome, cor=excluded.cor, ordem=excluded.ordem, fluxo=excluded.fluxo
        """, (id, fluxo, nome, cor, ordem))


def get_stats():
    with get_conn() as conn:
        situacoes = conn.execute("""
            SELECT situacao, COUNT(*) as total FROM orders GROUP BY situacao ORDER BY total DESC
        """).fetchall()

        substatuses = conn.execute("""
            SELECT s.id, s.nome, s.cor, COUNT(o.op) as total
            FROM substatuses s
            LEFT JOIN orders o ON o.substatus_id = s.id AND o.situacao LIKE '%Em Produ%'
            WHERE s.ativo = 1
            GROUP BY s.id ORDER BY s.ordem
        """).fetchall()

        sem_substatus = conn.execute("""
            SELECT COUNT(*) as total FROM orders
            WHERE situacao LIKE '%Em Produ%' AND substatus_id IS NULL
        """).fetchone()

        return {
            "por_situacao": [dict(r) for r in situacoes],
            "por_substatus": [dict(r) for r in substatuses],
            "em_producao_sem_substatus": sem_substatus["total"] if sem_substatus else 0,
        }


def load_from_html(html: str) -> int:
    """Extrai todos os registros de uma resposta HTML do ScriptCase e salva no banco.
    Preserva substatus_id já existentes (não sobrescreve em pedidos já atualizados)."""

    def clean(text: str) -> str:
        text = re.sub(r'<[^>]+>', ' ', text)
        text = html_mod.unescape(text)   # converte &ccedil; → ç, &atilde; → ã, etc.
        return ' '.join(text.split()).strip()

    FIELD_MAP = {
        'css_gsp_ptasituacao_grid_line':              'situacao',
        'css_gsp_mtdcodigo_grid_line':               'motivo_desistencia',
        'css_parceiro_grid_line':                    'parceiro',
        'css_gsp_ptacodigo_grid_line':               'op',
        'css_gsp_pta_pedido_fabrica_grid_line':      'pedido_fabrica',
        'css_gsp_pta_pedido_parceiro_grid_line':     'pedido_parceiro',
        'css_razaosocial_grid_line':                 'razao_social',
        'css_fantasia_grid_line':                    'fantasia',
        'css_gsp_ptanomeconsumidor_grid_line':       'nome_consumidor',
        'css_gsp_ptadata_grid_line':                 'data_orcamento',
        'css_gsp_ptadatapedido_grid_line':           'data_pedido',
        'css_gsp_ptaultimaalteracao_grid_line':      'ultima_alteracao',
        'css_gsp_ptaqtdportas_grid_line':            'qtd_portas',
        'css_gsp_ptaqtdvidros_grid_line':            'qtd_vidros',
        'css_gsp_ptaqtdesquadrias_grid_line':        'qtd_quadros',
        'css_gsp_ptaqtdcamarim_grid_line':           'qtd_camarim',
        'css_gsp_ptaqtdestrutural_grid_line':        'qtd_estrutural',
        'css_gsp_ptaqtdtotal_grid_line':             'qtd_total',
        'css_gsp_ptavalortotal_grid_line':           'valor_total',
        'css_vendedorpedido_grid_line':              'vendedor_pedido',
        'css_gsp_ptaandamento_grid_line':            'andamento',
        'css_regiao_grid_line':                      'regiao',
        'css_gsp_ptaapcliente_grid_line':            'aprov_cliente',
        'css_gsp_ptaapfilial_grid_line':             'aprov_filial',
        'css_gsp_ptaapempresa_grid_line':            'aprov_empresa',
    }

    def to_int(v: str) -> int:
        try:
            return int(v.replace('.', '').replace(',', ''))
        except Exception:
            return 0

    rows = []
    for i in range(1, 100_000):
        idx = html.find(f'id="SC_ancor{i}"')
        if idx < 0:
            break
        next_idx = html.find(f'id="SC_ancor{i + 1}"', idx + 20)
        row_html = html[idx: next_idx if next_idx > 0 else idx + 15_000]

        tds = re.findall(r'<TD[^>]*class="([^"]+)"[^>]*>(.*?)</TD>', row_html, re.DOTALL | re.IGNORECASE)
        record: dict = {}
        for cls, content in tds:
            for css_key, field in FIELD_MAP.items():
                if css_key in cls:
                    record[field] = clean(content)
                    break

        if not record.get('op'):
            continue

        rows.append({
            'op':               record.get('op', ''),
            'parceiro':         record.get('parceiro', ''),
            'razao_social':     record.get('razao_social', ''),
            'fantasia':         record.get('fantasia', ''),
            'nome_consumidor':  record.get('nome_consumidor', ''),
            'situacao':         record.get('situacao', ''),
            'data_orcamento':   record.get('data_orcamento', ''),
            'data_pedido':      record.get('data_pedido', ''),
            'ultima_alteracao': record.get('ultima_alteracao', ''),
            'qtd_portas':       to_int(record.get('qtd_portas', '0')),
            'qtd_vidros':       to_int(record.get('qtd_vidros', '0')),
            'qtd_quadros':      to_int(record.get('qtd_quadros', '0')),
            'qtd_camarim':      to_int(record.get('qtd_camarim', '0')),
            'qtd_estrutural':   to_int(record.get('qtd_estrutural', '0')),
            'qtd_total':        to_int(record.get('qtd_total', '0')),
            'valor_total':      record.get('valor_total', ''),
            'vendedor_pedido':  record.get('vendedor_pedido', ''),
            'andamento':        record.get('andamento', ''),
            'regiao':           record.get('regiao', ''),
            'pedido_fabrica':   record.get('pedido_fabrica', ''),
            'pedido_parceiro':  record.get('pedido_parceiro', ''),
            'aprov_cliente':    record.get('aprov_cliente', ''),
            'aprov_filial':     record.get('aprov_filial', ''),
            'aprov_empresa':    record.get('aprov_empresa', ''),
            'raw_json':         json.dumps(record, ensure_ascii=False),
        })

    if not rows:
        return 0

    with get_conn() as conn:
        conn.executemany("""
            INSERT INTO orders (
                op, parceiro, razao_social, fantasia, nome_consumidor, situacao,
                data_orcamento, data_pedido, ultima_alteracao,
                qtd_portas, qtd_vidros, qtd_quadros, qtd_camarim, qtd_estrutural,
                qtd_total, valor_total, vendedor_pedido, andamento, regiao,
                pedido_fabrica, pedido_parceiro, aprov_cliente, aprov_filial,
                aprov_empresa, raw_json
            ) VALUES (
                :op, :parceiro, :razao_social, :fantasia, :nome_consumidor, :situacao,
                :data_orcamento, :data_pedido, :ultima_alteracao,
                :qtd_portas, :qtd_vidros, :qtd_quadros, :qtd_camarim, :qtd_estrutural,
                :qtd_total, :valor_total, :vendedor_pedido, :andamento, :regiao,
                :pedido_fabrica, :pedido_parceiro, :aprov_cliente, :aprov_filial,
                :aprov_empresa, :raw_json
            ) ON CONFLICT(op) DO UPDATE SET
                parceiro        = excluded.parceiro,
                razao_social    = excluded.razao_social,
                fantasia        = excluded.fantasia,
                nome_consumidor = excluded.nome_consumidor,
                situacao        = excluded.situacao,
                data_orcamento  = excluded.data_orcamento,
                data_pedido     = excluded.data_pedido,
                ultima_alteracao= excluded.ultima_alteracao,
                qtd_portas      = excluded.qtd_portas,
                qtd_vidros      = excluded.qtd_vidros,
                qtd_quadros     = excluded.qtd_quadros,
                qtd_camarim     = excluded.qtd_camarim,
                qtd_estrutural  = excluded.qtd_estrutural,
                qtd_total       = excluded.qtd_total,
                valor_total     = excluded.valor_total,
                vendedor_pedido = excluded.vendedor_pedido,
                andamento       = excluded.andamento,
                regiao          = excluded.regiao,
                pedido_fabrica  = excluded.pedido_fabrica,
                pedido_parceiro = excluded.pedido_parceiro,
                aprov_cliente   = excluded.aprov_cliente,
                aprov_filial    = excluded.aprov_filial,
                aprov_empresa   = excluded.aprov_empresa,
                raw_json        = excluded.raw_json
                -- substatus_id intencionalmente NÃO atualizado para preservar atualizações manuais
        """, rows)

    return len(rows)


# ── Auth helpers ─────────────────────────────────────────────────────────────

def _hash_password(password: str, salt: str = None):
    if salt is None:
        salt = secrets.token_hex(32)
    h = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 260000)
    return h.hex(), salt


def _verify_password(password: str, stored_hash: str, salt: str) -> bool:
    computed, _ = _hash_password(password, salt)
    return secrets.compare_digest(computed, stored_hash)


def create_user(username: str, password: str, role: str = 'USER') -> int:
    pwd_hash, salt = _hash_password(password)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO auth_users (username, password_hash, salt, role) VALUES (?,?,?,?)",
            (username, pwd_hash, salt, role)
        )
        return cur.lastrowid


def authenticate_user(username: str, password: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM auth_users WHERE username = ?", (username,)).fetchone()
    if not row:
        return None
    user = dict(row)
    if not _verify_password(password, user['password_hash'], user['salt']):
        return None
    return user


def get_user_by_id(user_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_all_users() -> list:
    with get_conn() as conn:
        users = conn.execute(
            "SELECT id, username, role, created_at FROM auth_users ORDER BY id"
        ).fetchall()
        result = []
        for u in users:
            ud = dict(u)
            subs = conn.execute(
                "SELECT substatus_id FROM user_substatuses WHERE user_id = ?", (ud['id'],)
            ).fetchall()
            ud['substatus_ids'] = [r[0] for r in subs]
            result.append(ud)
        return result


def update_user(user_id: int, username: str = None, role: str = None, password: str = None):
    with get_conn() as conn:
        if username is not None:
            conn.execute("UPDATE auth_users SET username = ? WHERE id = ?", (username, user_id))
        if role is not None:
            conn.execute("UPDATE auth_users SET role = ? WHERE id = ?", (role, user_id))
        if password is not None:
            pwd_hash, salt = _hash_password(password)
            conn.execute(
                "UPDATE auth_users SET password_hash = ?, salt = ? WHERE id = ?",
                (pwd_hash, salt, user_id)
            )


def delete_user(user_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM user_substatuses WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM auth_users WHERE id = ?", (user_id,))


def change_user_password(user_id: int, old_password: str, new_password: str) -> bool:
    user = get_user_by_id(user_id)
    if not user:
        return False
    if not _verify_password(old_password, user['password_hash'], user['salt']):
        return False
    update_user(user_id, password=new_password)
    return True


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(48)
    with get_conn() as conn:
        conn.execute("INSERT INTO auth_sessions (token, user_id) VALUES (?,?)", (token, user_id))
    return token


def get_session(token: str):
    with get_conn() as conn:
        row = conn.execute("""
            SELECT u.id, u.username, u.role
            FROM auth_sessions s
            JOIN auth_users u ON s.user_id = u.id
            WHERE s.token = ?
        """, (token,)).fetchone()
        return dict(row) if row else None


def delete_session(token: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))


def get_user_substatuses(user_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT substatus_id FROM user_substatuses WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [r[0] for r in rows]


def set_user_substatuses(user_id: int, substatus_ids: list):
    with get_conn() as conn:
        conn.execute("DELETE FROM user_substatuses WHERE user_id = ?", (user_id,))
        conn.executemany(
            "INSERT INTO user_substatuses (user_id, substatus_id) VALUES (?,?)",
            [(user_id, sid) for sid in substatus_ids]
        )


def get_history(op: str = None, limit: int = 50):
    sql = """
        SELECT h.*, o.razao_social, o.parceiro
        FROM substatus_history h
        LEFT JOIN orders o ON h.op = o.op
    """
    params = []
    if op:
        sql += " WHERE h.op = ?"
        params.append(op)
    sql += " ORDER BY h.atualizado_em DESC LIMIT ?"
    params.append(limit)

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
