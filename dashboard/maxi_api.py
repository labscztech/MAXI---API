"""
Maxi Portas – Cliente da API oficial de Pedidos/Orçamentos.

Endpoint: POST https://www.maxiportas.com.br/ap_pedidos/index.php?OP_Dados=null
Headers:  Token, Empresa, Pedido, Modelo
Modelo 1: retorno detalhado com cabeçalho, itens e matérias-primas.
"""

import urllib.request
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

API_URL = "https://www.maxiportas.com.br/ap_pedidos/index.php?OP_Dados=null"
CONFIG_PATH = Path(__file__).parent / "config.json"

# Mapeamento de código de situação → descrição legível
SITUACAO_MAP = {
    "A": "Pedido Cancelado",
    "B": "Orçamento",
    "C": "Orçamento Perdido",
    "D": "Pedido não Aprovado",
    "E": "Aprovado pelo Cliente",
    "F": "Aprovado pelo Parceiro",
    "G": "Aprovado pela Fábrica",
    "H": "Em Produção",
    "I": "Produzido (Aguardando entrega ao Parceiro)",
    "J": "Entregue ao Parceiro",
    "K": "Disponível ao Cliente",
    "L": "Entregue ao Cliente",
}

# Mapeamento de ITEM_TIPO → campo de quantidade correspondente
ITEM_TIPO_FIELD = {
    0: "qtd_portas",
    1: "qtd_vidros",
    2: "qtd_quadros",
    5: "qtd_camarim",
    6: "qtd_estrutural",
}


# ── Config ────────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_api_config(token: str, empresa: str):
    """Salva token e empresa no config.json."""
    cfg = _load_config()
    cfg["api_token"] = token
    cfg["api_empresa"] = str(empresa)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def get_api_config() -> tuple[str, str]:
    """Retorna (token, empresa) salvos no config."""
    cfg = _load_config()
    return cfg.get("api_token", ""), cfg.get("api_empresa", "")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_str(value) -> str:
    """Converte valor da API para string limpa. Campos vazios vêm como [' ']."""
    if isinstance(value, list):
        return ""
    if value is None:
        return ""
    return str(value).strip()


def _safe_float(value) -> float:
    try:
        s = _safe_str(value)
        return float(s) if s else 0.0
    except (ValueError, TypeError):
        return 0.0


def _safe_int(value) -> int:
    try:
        s = _safe_str(value)
        return int(float(s)) if s else 0
    except (ValueError, TypeError):
        return 0


def _format_date(value) -> str:
    """Converte 'aaaa-mm-dd' → 'dd/mm/aaaa' para consistência com o scraper."""
    s = _safe_str(value)
    if not s or len(s) < 10:
        return s
    try:
        parts = s.split("-")
        if len(parts) == 3:
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
    except Exception:
        pass
    return s


# ── Fetch da API ──────────────────────────────────────────────────────────────

def fetch_order_from_api(op: str, token: str = "", empresa: str = "") -> dict | None:
    """
    Busca dados de um pedido/orçamento específico via API.

    Retorna um dict compatível com o schema do banco de dados,
    ou None se o pedido não for encontrado.
    Levanta RuntimeError em caso de erro de comunicação.
    """
    if not token or not empresa:
        token, empresa = get_api_config()
    if not token or not empresa:
        raise RuntimeError("Credenciais da API não configuradas (Token/Empresa).")

    headers = {
        "Token": token,
        "Empresa": str(empresa),
        "Pedido": str(op),
        "Modelo": "1",
    }

    req = urllib.request.Request(API_URL, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except Exception as e:
        logger.error(f"Erro ao chamar API para OP {op}: {e}")
        raise RuntimeError(f"Erro de comunicação com a API: {e}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.error(f"Resposta inválida da API para OP {op}")
        raise RuntimeError("Resposta inválida da API (não é JSON).")

    if data.get("status") != 200:
        msg = data.get("message", "Erro desconhecido")
        logger.warning(f"API retornou status {data.get('status')} para OP {op}: {msg}")
        return None

    return _parse_api_response(data)


def _parse_api_response(data: dict) -> dict:
    """Converte a resposta da API Modelo 1 para o formato do banco local."""
    pedido = data.get("dados", {}).get("PEDIDO", {})
    cab = pedido.get("CABECALHO", {})
    cliente = cab.get("PEDIDO_CLIENTE", {})
    valor = cab.get("PEDIDO_VALOR", {})
    itens_raw = pedido.get("ITENS", [])

    # Situação: mapear código → descrição legível
    sit_code = _safe_str(cab.get("PEDIDO_SITUACAO"))
    situacao = SITUACAO_MAP.get(sit_code, sit_code)

    # Status P/O
    status = _safe_str(cab.get("PEDIDO_STATUS"))

    # Contar itens por tipo
    qtd = {"qtd_portas": 0, "qtd_vidros": 0, "qtd_quadros": 0, "qtd_camarim": 0, "qtd_estrutural": 0}
    qtd_total = 0

    items_list = []
    if isinstance(itens_raw, dict) and "ITEM" in itens_raw:
        items_list = itens_raw["ITEM"]
        if isinstance(items_list, dict):
            items_list = [items_list]
    elif isinstance(itens_raw, list):
        items_list = itens_raw

    for item in items_list:
        tipo = _safe_int(item.get("ITEM_TIPO", 9))
        item_qty = int(_safe_float(item.get("ITEM_VALORES", {}).get("ITEM_QUANTIDADE", 0)))
        field = ITEM_TIPO_FIELD.get(tipo)
        if field:
            qtd[field] += item_qty
        qtd_total += item_qty

    # Montar o andamento baseado na situação
    andamento = situacao

    # Valor total formatado
    valor_total_num = _safe_float(valor.get("PEDIDO_VALOR_TOTAL", 0))
    valor_total_str = f"{valor_total_num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    record = {
        "op":               _safe_str(cab.get("PEDIDO_CODIGO")),
        "parceiro":         _safe_str(cliente.get("PEDIDO_CLIENTE_RAZAO_SOCIAL")),
        "razao_social":     _safe_str(cliente.get("PEDIDO_CLIENTE_RAZAO_SOCIAL")),
        "fantasia":         "",
        "nome_consumidor":  "",
        "situacao":         situacao,
        "data_orcamento":   _format_date(cab.get("PEDIDO_DATA")),
        "data_pedido":      _format_date(cab.get("PEDIDO_APROVACAO")),
        "ultima_alteracao":  _format_date(cab.get("PEDIDO_ULTIMA_ALTERACAO")),
        "qtd_portas":       qtd["qtd_portas"],
        "qtd_vidros":       qtd["qtd_vidros"],
        "qtd_quadros":      qtd["qtd_quadros"],
        "qtd_camarim":      qtd["qtd_camarim"],
        "qtd_estrutural":   qtd["qtd_estrutural"],
        "qtd_total":        qtd_total,
        "valor_total":      valor_total_str,
        "vendedor_pedido":  _safe_str(cab.get("PEDIDO_VENDEDOR_NOME")),
        "andamento":        andamento,
        "regiao":           _safe_str(cliente.get("PEDIDO_CLIENTE_END_UF")),
        "pedido_fabrica":   "",
        "pedido_parceiro":  "",
        "aprov_cliente":    _format_date(cab.get("PEDIDO_APROVACAO")),
        "aprov_filial":     _format_date(cab.get("PEDIDO_APROVACAO_PARCEIRO")),
        "aprov_empresa":    _format_date(cab.get("PEDIDO_APROVACAO_FABRICA")),
        # Campos extras da API que não existem no scraper
        "cliente_cnpj_cpf": _safe_str(cliente.get("PEDIDO_CLIENTE_CNPJ_CPF")),
        "cliente_fone":     _safe_str(cliente.get("PEDIDO_CLIENTE_FONE")),
        "cliente_email":    _safe_str(cliente.get("PEDIDO_CLIENTE_E_MAIL")),
        "cliente_cidade":   _safe_str(cliente.get("PEDIDO_CLIENTE_END_CIDADE")),
        "cliente_uf":       _safe_str(cliente.get("PEDIDO_CLIENTE_END_UF")),
        "previsao_entrega": _format_date(cab.get("PEDIDO_PREVISAO_ENTREGA")),
        "data_producao":    _format_date(cab.get("PEDIDO_ENTROU_EM_PRODUCAO")),
        "data_produzido":   _format_date(cab.get("PEDIDO_PRODUZIDO")),
        "data_entregue_parceiro": _format_date(cab.get("PEDIDO_ENTREGUE_AO_PARCEIRO")),
        "data_entregue_cliente":  _format_date(cab.get("PEDIDO_ENTREGUE_AO_CLIENTE")),
        "raw_json":         json.dumps(data.get("dados", {}), ensure_ascii=False),
    }

    return record


def extract_items_from_raw(raw_json_str: str) -> list[dict]:
    """Extrai lista de itens a partir do raw_json já salvo no banco (dados.PEDIDO.ITENS)."""
    try:
        data = json.loads(raw_json_str)
    except Exception:
        return []

    pedido = data.get("PEDIDO", {})
    itens_raw = pedido.get("ITENS", [])

    items_list: list = []
    if isinstance(itens_raw, dict) and "ITEM" in itens_raw:
        items_list = itens_raw["ITEM"]
        if isinstance(items_list, dict):
            items_list = [items_list]
    elif isinstance(itens_raw, list):
        items_list = itens_raw

    result = []
    for i, item in enumerate(items_list):
        if not isinstance(item, dict):
            continue
        valores = item.get("ITEM_VALORES", {})
        if not isinstance(valores, dict):
            valores = {}

        qty = int(_safe_float(valores.get("ITEM_QUANTIDADE", 0)) or _safe_float(item.get("ITEM_QUANTIDADE", 0)))

        descricao = (
            _safe_str(item.get("ITEM_DESCRICAO"))
            or _safe_str(item.get("ITEM_REFERENCIA"))
            or _safe_str(item.get("ITEM_CODIGO"))
        )

        result.append({
            "item_seq": i + 1,
            "item_tipo": _safe_int(item.get("ITEM_TIPO", 0)),
            "item_codigo": _safe_str(item.get("ITEM_CODIGO", "")),
            "item_descricao": descricao,
            "quantidade": qty,
            "valor_total": _safe_str(valores.get("ITEM_VALOR_TOTAL", "")),
            "raw_json": json.dumps(item, ensure_ascii=False),
        })

    return result


def fetch_multiple_orders(ops: list[str], token: str = "", empresa: str = "") -> list[dict]:
    """
    Busca vários pedidos sequencialmente.
    Retorna lista de dicts (ignora pedidos não encontrados).
    """
    results = []
    for op in ops:
        try:
            record = fetch_order_from_api(op, token, empresa)
            if record:
                results.append(record)
        except RuntimeError:
            continue
    return results


# ── Fetch Lista de OPs ────────────────────────────────────────────────────────

API_LISTA_URL = "https://www.maxiportas.com.br/ap_pedidos/index.php?OP_Lista=null"

def fetch_orders_list(dinicial: str, dfinal: str, status="T", situacao="T", token: str = "", empresa: str = "") -> list[dict]:
    """
    Busca a lista de pedidos em um período de até 30 dias.
    Retorna uma lista de dicionários já no formato simplificado do banco.
    """
    if not token or not empresa:
        token, empresa = get_api_config()
    if not token or not empresa:
        raise RuntimeError("Credenciais da API não configuradas (Token/Empresa).")

    headers = {
        "Token": token,
        "Empresa": str(empresa),
        "Status": status,
        "Situacao": situacao,
        "Dinicial": dinicial,
        "Dfinal": dfinal,
    }

    req = urllib.request.Request(API_LISTA_URL, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except Exception as e:
        logger.error(f"Erro ao chamar API Lista entre {dinicial} e {dfinal}: {e}")
        raise RuntimeError(f"Erro de comunicação com a API: {e}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("Resposta inválida da API (não é JSON).")

    if data.get("status") != 200:
        return []

    itens_raw = data.get("dados", {}).get("LISTA", {}).get("ITEM", [])
    if isinstance(itens_raw, dict):
        itens_raw = [itens_raw]

    results = []
    for item in itens_raw:
        # Extrai e formata dados disponíveis na listagem
        record = {
            "op":               _safe_str(item.get("PEDIDO_CODIGO")),
            "parceiro":         _safe_str(item.get("PEDIDO_CLIENTE_RAZAO_SOCIAL")),
            "razao_social":     _safe_str(item.get("PEDIDO_CLIENTE_RAZAO_SOCIAL")),
            "cliente_cnpj_cpf": _safe_str(item.get("PEDIDO_CLIENTE_CNPJ_CPF")),
            "situacao":         _safe_str(item.get("PEDIDO_SITUACAO_DESCRICAO")),
            "data_orcamento":   _format_date(item.get("PEDIDO_DATA")),
            "data_pedido":      "",  # não vem na listagem
            "ultima_alteracao": _format_date(item.get("PEDIDO_ULTIMA_ALTERACAO")),
            "valor_total":      str(_safe_float(item.get("PEDIDO_VALOR", {}).get("PEDIDO_VALOR_TOTAL", 0))),
            "andamento":        _safe_str(item.get("PEDIDO_SITUACAO_DESCRICAO")),
            "raw_json":         json.dumps(item, ensure_ascii=False)
        }
        if record["op"]:
            results.append(record)

    return results

def sync_last_90_days_orders(token: str = "", empresa: str = "") -> list[dict]:
    """
    Busca a listagem de pedidos dos últimos 90 dias,
    quebrando em 3 request de 30 dias para respeitar o limite da API.
    """
    from datetime import datetime, timedelta
    
    today = datetime.now()
    results = []
    
    # 3 blocos de 30 dias
    for i in range(3):
        df = today - timedelta(days=30 * i)
        di = df - timedelta(days=29) # Max 30 days diff
        
        chunk = fetch_orders_list(
            dinicial=di.strftime("%Y-%m-%d"),
            dfinal=df.strftime("%Y-%m-%d"),
            token=token,
            empresa=empresa
        )
        results.extend(chunk)
        
    return results
