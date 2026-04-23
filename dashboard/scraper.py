"""
Maxi Portas – Scraper com auto-login e navegação completa.

Fluxo de sessão:
  1. GET /Inicio/  → extrai csrf_token, script_case_session, script_case_init
  2. POST /Inicio/ → autentica; resposta contém form JS que redireciona para /Menu_Empresas/
  3. POST /Menu_Empresas/ (seguindo o form) → menu principal
  4. GET /Menu_Empresas/Menu_Empresas_form_php.php?...Menu_Empresas_Acessos...
     → form com action=/Menu_Empresas_Acessos/
  5. POST /Menu_Empresas_Acessos/ → menu de acesso com link para a grade
  6. GET /Menu_Empresas_Acessos/...form_php.php?...grid_gsp_portas_AdmEmp...
     → form com action=/grid_gsp_portas_AdmEmp/  (inclui nmgp_parms do usuário)
  7. POST /grid_gsp_portas_AdmEmp/ → primeira carga (detecta total de registros)
  8. POST /grid_gsp_portas_AdmEmp/ com nmgp_quant_linhas=N → todos os registros
"""

import re
import urllib.request
import urllib.parse
import http.cookiejar
import json
from pathlib import Path

BASE_URL    = "https://www.maxiportas.com.br"
LOGIN_URL   = f"{BASE_URL}/Inicio/"
GRID_URL    = f"{BASE_URL}/grid_gsp_portas_AdmEmp/"
CONFIG_PATH = Path(__file__).parent / "config.json"


# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_config(data: dict):
    current = load_config()
    current.update(data)
    CONFIG_PATH.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")


def get_credentials() -> tuple[str, str]:
    cfg = load_config()
    return cfg.get("usuario", ""), cfg.get("senha", "")


# ── HTTP session ──────────────────────────────────────────────────────────────

def _build_opener():
    """Um único opener+jar para toda a sessão. O CookieJar gerencia cookies automaticamente."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPRedirectHandler(),
    )
    return opener, jar


def _get(opener, url: str, referer: str = "") -> str:
    h = {"User-Agent": "Mozilla/5.0", "Accept": "text/html,*/*;q=0.8"}
    if referer:
        h["Referer"] = referer
    with opener.open(urllib.request.Request(url, headers=h), timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def _post(opener, url: str, fields: dict, referer: str = "", timeout: int = 90) -> str:
    h = {
        "User-Agent":   "Mozilla/5.0",
        "Accept":       "text/html,*/*;q=0.8",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    if referer:
        h["Referer"] = referer
    data = urllib.parse.urlencode(fields).encode()
    with opener.open(urllib.request.Request(url, data=data, headers=h), timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


# ── HTML parsing helpers ───────────────────────────────────────────────────────

def _extract_hidden(html: str, name: str) -> str:
    """Extrai value de <input type=hidden name='X'>."""
    esc = re.escape(name)
    m = re.search(
        rf'name=["\'][^"\']*{esc}[^"\']*["\'][^>]*value=["\']([^"\']*)["\']',
        html, re.IGNORECASE
    )
    if m:
        return m.group(1)
    m2 = re.search(
        rf'value=["\']([^"\']*)["\'][^>]*name=["\'][^"\']*{esc}[^"\']*["\']',
        html, re.IGNORECASE
    )
    if m2:
        return m2.group(1)
    return ""


def _parse_form(html: str) -> tuple[str, dict]:
    """
    Extrai (action_url, {name: value}) do primeiro form.
    Suporta action via atributo HTML e via `document.xxx.action = "..."`.
    """
    # Action: primeiro tenta atributo HTML do <form>
    m = re.search(r'<form\b[^>]*\baction=["\']([^"\']*)["\']', html, re.IGNORECASE)
    if m and m.group(1):
        action = m.group(1)
    else:
        # Fallback: JS `document.Fredir.action = "/Menu_Empresas/";`
        m = re.search(r'document\.\w+\.action\s*=\s*["\']([^"\']+)["\']', html)
        action = m.group(1) if m else ""

    # Campos: todos os <input> com name + value
    fields: dict[str, str] = {}
    for tag in re.finditer(r"<input\b[^>]*>", html, re.IGNORECASE):
        t = tag.group(0)
        n = re.search(r'\bname=["\']([^"\']+)["\']', t)
        v = re.search(r'\bvalue=["\']([^"\']*)["\']', t)
        if n and v:
            fields[n.group(1)] = v.group(1)

    return action, fields


def _find_nav_link(html: str, app_name: str, page_url: str) -> str:
    """Encontra o link de navegação para um app ScriptCase em uma página de menu."""
    m = re.search(
        rf'([\w./]+_form_php\.php\?[^"\'<\s]*sc_apl_menu={re.escape(app_name)}[^"\'<\s]*)',
        html, re.IGNORECASE
    )
    if not m:
        return ""
    rel = urllib.parse.unquote(m.group(1))
    if rel.startswith("/"):
        return BASE_URL + rel
    # Relativo ao diretório da página atual
    base_dir = re.sub(r"[^/]+$", "", page_url)
    return base_dir + rel


def _absolute_url(url: str) -> str:
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return BASE_URL + url
    return BASE_URL + "/" + url


def _is_login_page(html: str) -> bool:
    return 'name="usuario"' in html or "name='usuario'" in html


def _detect_total(html: str) -> int:
    """
    Detecta o total real de registros a partir de:
      1. Padrão "N de TOTAL" da barra de paginação do ScriptCase
      2. Variável JS sc_num_reg (total, diferente de scQtReg que reflete o page size)
    scQtReg é ignorado pois espelha nmgp_quant_linhas (page size), não o total real.
    """
    # Padrão "10 de 43386" da barra de navegação
    m = re.search(r'\b\d+\s+de\s+(\d{3,})', html, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        if val > 0:
            return val
    # Variável JS sc_num_reg (mais confiável que scQtReg)
    m = re.search(r'var\s+sc_num_reg\s*=\s*(\d+)', html)
    if m:
        val = int(m.group(1))
        if val > 0:
            return val
    # Fallback: maior SC_ancorN presente
    anchors = re.findall(r"SC_ancor(\d+)", html)
    return max((int(a) for a in anchors), default=0)


# ── Autenticação ──────────────────────────────────────────────────────────────

def _do_login(opener, jar, usuario: str, senha: str) -> str:
    """
    Realiza login e navega até /Menu_Empresas/.
    Após este passo, o jar contém a sessão autenticada para a app Menu_Empresas.
    Levanta RuntimeError em caso de falha.
    """
    # Passo 1: GET página de login
    login_page = _get(opener, LOGIN_URL)
    if len(login_page) < 500:
        raise RuntimeError("Página de login inacessível.")

    csrf       = _extract_hidden(login_page, "csrf_token")
    sc_init    = _extract_hidden(login_page, "script_case_init")
    sc_session = _extract_hidden(login_page, "script_case_session")

    if not sc_session:
        for c in jar:
            if "PHPSESSID" in c.name:
                sc_session = c.value
                break

    # Passo 2: POST credenciais
    login_result = _post(opener, LOGIN_URL, {
        "nm_form_submit":       "1",
        "nmgp_idioma_novo":     "",
        "nmgp_schema_f":        "",
        "nmgp_url_saida":       "",
        "bok":                  "OK",
        "nmgp_opcao":           "gravar",
        "nmgp_ancora":          "",
        "nmgp_num_form":        "",
        "nmgp_parms":           "",
        "script_case_init":     sc_init,
        "script_case_session":  sc_session,
        "NM_cancel_return_new": "",
        "csrf_token":           csrf,
        "_sc_force_mobile":     "",
        "usuario":              usuario,
        "senha":                senha,
    }, referer=LOGIN_URL)

    if _is_login_page(login_result):
        erros = re.findall(
            r'class="[^"]*(?:scErrorMessage|alert)[^"]*"[^>]*>(.*?)<',
            login_result, re.IGNORECASE
        )
        msg = " | ".join(re.sub(r"<[^>]+>", "", e).strip() for e in erros if e.strip())
        raise RuntimeError(f"Login falhou: {msg or 'usuário ou senha incorretos'}")

    # Passo 3: seguir o form POST para /Menu_Empresas/ e retornar o HTML do menu
    action, fields = _parse_form(login_result)
    if action:
        return _post(opener, _absolute_url(action), fields, referer=LOGIN_URL)
    return login_result


# ── Navegação até o grid ──────────────────────────────────────────────────────

def _navigate_to_grid(opener, menu_html: str) -> tuple[str, str]:
    """
    Navega Menu_Empresas → Menu_Empresas_Acessos → grid_gsp_portas_AdmEmp.

    Recebe o HTML do menu principal (retornado por _do_login).
    Retorna (html_primeira_carga, script_case_init).
    A primeira carga já contém os registros da página padrão.
    """
    menu_url = _absolute_url("/Menu_Empresas/")

    # Passo 4: encontrar e acessar link para Menu_Empresas_Acessos
    if _is_login_page(menu_html):
        raise RuntimeError("Sessão inválida ao carregar Menu_Empresas.")

    nav_acessos = _find_nav_link(menu_html, "Menu_Empresas_Acessos", menu_url)
    if not nav_acessos:
        raise RuntimeError("Link para Menu_Empresas_Acessos não encontrado no menu.")

    acesso_html = _get(opener, nav_acessos, referer=menu_url)
    action_acessos, fields_acessos = _parse_form(acesso_html)
    if not action_acessos:
        raise RuntimeError("Form de navegação para Menu_Empresas_Acessos não encontrado.")

    # Passo 5: POST para Menu_Empresas_Acessos
    acessos_url = _absolute_url(action_acessos)
    acessos_html = _post(opener, acessos_url, fields_acessos, referer=nav_acessos)

    # Passo 6: encontrar e acessar link para grid_gsp_portas_AdmEmp
    nav_grid = _find_nav_link(acessos_html, "grid_gsp_portas_AdmEmp", acessos_url)
    if not nav_grid:
        raise RuntimeError("Link para grid_gsp_portas_AdmEmp não encontrado no menu Acessos.")

    grid_nav_html = _get(opener, nav_grid, referer=acessos_url)
    action_grid, fields_grid = _parse_form(grid_nav_html)
    if not action_grid:
        raise RuntimeError("Form de navegação para o grid não encontrado.")

    # Passo 7: POST para o grid – primeira carga
    first_html = _post(opener, _absolute_url(action_grid), fields_grid, referer=nav_grid, timeout=90)

    if _is_login_page(first_html):
        raise RuntimeError("Sessão expirou ao carregar o grid.")
    if "não autorizado" in first_html.lower() or "nao autorizado" in first_html.lower():
        raise RuntimeError("Usuário não autorizado no grid.")

    sc_init = _extract_hidden(first_html, "script_case_init") or "1"
    return first_html, sc_init


# ── Fetch de registros ────────────────────────────────────────────────────────

def _post_grid(opener, jar, sc_init: str, qt_linhas: int) -> str:
    """POST para trocar a quantidade de linhas exibidas no grid."""
    session = next((c.value for c in jar if c.name == "PHPSESSID"), "")
    return _post(opener, GRID_URL, {
        "script_case_init":    sc_init,
        "script_case_session": session,
        "nmgp_opcao":          "muda_qt_linhas",
        "nmgp_quant_linhas":   str(qt_linhas),
    }, referer=GRID_URL, timeout=90)


# ── API pública ────────────────────────────────────────────────────────────────

# Máximo de registros a buscar por sync (grid ordenado por OP desc = mais recentes primeiro).
# 1000 cobre ~1-2 meses de pedidos sem sobrecarregar (≈13MB de HTML).
MAX_FETCH = 1_000


def fetch_all_records(usuario: str = "", senha: str = "") -> tuple[str, int]:
    """
    Login completo → navegação até o grid → retorna (html, qtd_registros).

    Busca os MAX_FETCH registros mais recentes (grid ordenado por OP desc).
    Levanta RuntimeError se qualquer etapa falhar.
    """
    if not usuario:
        usuario, senha = get_credentials()
    if not usuario:
        raise RuntimeError("Credenciais não configuradas. Acesse Configurações no dashboard.")

    opener, jar = _build_opener()

    # 1. Login + chegar até Menu_Empresas
    menu_html = _do_login(opener, jar, usuario, senha)

    # 2. Navegar até o grid — primeira carga (default 10 registros) + sc_init
    first_html, sc_init = _navigate_to_grid(opener, menu_html)

    # 3. Detectar total real de registros no servidor
    total = _detect_total(first_html)
    if total == 0:
        total = MAX_FETCH  # fallback se paginação não encontrada

    # 4. Quantos registros buscar: min(total, MAX_FETCH)
    qt = min(total, MAX_FETCH)

    # Se a primeira carga já contém tudo que queremos, usá-la
    first_count = len(re.findall(r'id="SC_ancor\d+"', first_html))
    if first_count >= qt:
        return first_html, first_count

    # 5. Buscar com qt_linhas=qt
    all_html = _post_grid(opener, jar, sc_init, qt)
    found = len(re.findall(r'id="SC_ancor\d+"', all_html))

    return all_html, found


# ── Compatibilidade legada ─────────────────────────────────────────────────────

def login(usuario: str, senha: str) -> dict:
    """Retorna dict de cookies após login. Para uso standalone."""
    opener, jar = _build_opener()
    _do_login(opener, jar, usuario, senha)  # return value (menu HTML) ignored here
    return {c.name: c.value for c in jar}
