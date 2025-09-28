import os, re, time, json
import pandas as pd
import requests
from datetime import datetime, timezone
from sqlalchemy import create_engine, text

# =========================
# CONFIGURAÇÕES
# =========================
# 1) Excel de entrada com uma coluna "numeroProcesso"
lista_processos = "processos.xlsx"

# 2) Banco SQLite de saída
db_path = "datajud_processos.db"

# 3) Tribunais a consultar
#    Você pode adicionar outros endpoints conforme a necessidade
endpoints = {
    # "TRT1": "https://api-publica.datajud.cnj.jus.br/api_publica_trt1/_search",
    "TJAC": "https://api-publica.datajud.cnj.jus.br/api_publica_tjac/_search",
    "TJAL": "https://api-publica.datajud.cnj.jus.br/api_publica_tjal/_search",
    "TJAM": "https://api-publica.datajud.cnj.jus.br/api_publica_tjam/_search",
    "TJAP": "https://api-publica.datajud.cnj.jus.br/api_publica_tjap/_search",
    "TJBA": "https://api-publica.datajud.cnj.jus.br/api_publica_tjba/_search",
    "TJCE": "https://api-publica.datajud.cnj.jus.br/api_publica_tjce/_search",
    "TJDFT": "https://api-publica.datajud.cnj.jus.br/api_publica_tjdft/_search",
    "TJES": "https://api-publica.datajud.cnj.jus.br/api_publica_tjes/_search",
    "TJGO": "https://api-publica.datajud.cnj.jus.br/api_publica_tjgo/_search",
    "TJMA": "https://api-publica.datajud.cnj.jus.br/api_publica_tjma/_search",
    "TJMG": "https://api-publica.datajud.cnj.jus.br/api_publica_tjmg/_search",
    "TJMS": "https://api-publica.datajud.cnj.jus.br/api_publica_tjms/_search",
    "TJMT": "https://api-publica.datajud.cnj.jus.br/api_publica_tjmt/_search",
    "TJPA": "https://api-publica.datajud.cnj.jus.br/api_publica_tjpa/_search",
    "TJPB": "https://api-publica.datajud.cnj.jus.br/api_publica_tjpb/_search",
    "TJPE": "https://api-publica.datajud.cnj.jus.br/api_publica_tjpe/_search",
    "TJPI": "https://api-publica.datajud.cnj.jus.br/api_publica_tjpi/_search",
    "TJPR": "https://api-publica.datajud.cnj.jus.br/api_publica_tjpr/_search",
    "TJRJ": "https://api-publica.datajud.cnj.jus.br/api_publica_tjrj/_search",
    "TJRN": "https://api-publica.datajud.cnj.jus.br/api_publica_tjrn/_search",
    "TJRO": "https://api-publica.datajud.cnj.jus.br/api_publica_tjro/_search",
    "TJRR": "https://api-publica.datajud.cnj.jus.br/api_publica_tjrr/_search",
    "TJRS": "https://api-publica.datajud.cnj.jus.br/api_publica_tjrs/_search",
    "TJSC": "https://api-publica.datajud.cnj.jus.br/api_publica_tjsc/_search",
    "TJSE": "https://api-publica.datajud.cnj.jus.br/api_publica_tjse/_search",
    "TJSP": "https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search",
    "TJTO": "https://api-publica.datajud.cnj.jus.br/api_publica_tjto/_search"
}

# 4) API KEY
api_key = os.getenv("DATAJUD_APIKEY")
api_key = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
if not api_key:
    print("⚠️ Defina a variável de ambiente DATAJUD_APIKEY com a chave pública da Wiki.")
    # sys.exit(1)

# 5) Limites e tolerância
request_timeout = 30
sleep_between = 0.3  # pausa curta entre requisições
size = 10            # não precisamos de paginação para busca por número (retorno 1)

# =========================
# FUNÇÕES
# =========================
def normaliza_nup(n):
    """
    Remove tudo que não for dígito e corrige notação científica vinda do Excel.
    Aceita entradas como:
      '0425144-44.2016.8.19.0001' -> '04251444420168190001'
      1.01779912E+18 -> '101779912017501000'
    """
    s = str(n).strip()
    # Se veio como notação científica, pandas pode ter convertido para float
    if re.match(r"^\d+(\.\d+)?e\+\d+$", s, re.I):
        try:
            as_int = int(float(s))
            return re.sub(r"\D", "", str(as_int))
        except Exception:
            pass
    # remove tudo que não for dígito
    return re.sub(r"\D", "", s)

def consulta_por_numero(endpoint, numero):
    """
    Consulta um tribunal específico pelo numeroProcesso (sem máscara).
    Retorna o JSON (dict) ou erro em dict.
    """
    headers = {
        "Authorization": f"ApiKey {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "size": size,
        "query": {
            "match": {
                "numeroProcesso": numero
            }
        }
    }
    try:
        r = requests.post(endpoint, headers=headers, data=json.dumps(payload), timeout=request_timeout)
        if r.status_code == 200:
            return r.json()
        else:
            return {"_error": True, "status": r.status_code, "text": r.text}
    except requests.RequestException as e:
        return {"_error": True, "exception": str(e)}

def extrai_registros(hit_json):
    """
    A partir do JSON do DataJud, extrai 1..N documentos (hits) em duas tabelas:
      - processos: capa e campos principais
      - movimentos: lista de movimentos (1:N)
    Retorna (df_proc, df_mov)
    """
    if not hit_json or "hits" not in hit_json or "hits" not in hit_json["hits"]:
        return pd.DataFrame(), pd.DataFrame()

    procs, movs = [], []
    for h in hit_json["hits"]["hits"]:
        src = h.get("_source", {})
        numero = src.get("numeroProcesso")
        procs.append({
            "id": src.get("id"),
            "tribunal": src.get("tribunal"),
            "numeroProcesso": numero,
            "grau": src.get("grau"),
            "dataAjuizamento": src.get("dataAjuizamento"),
            "nivelSigilo": src.get("nivelSigilo"),
            "classe_codigo": (src.get("classe") or {}).get("codigo"),
            "classe_nome": (src.get("classe") or {}).get("nome"),
            "formato_codigo": (src.get("formato") or {}).get("codigo"),
            "formato_nome": (src.get("formato") or {}).get("nome"),
            "sistema_codigo": (src.get("sistema") or {}).get("codigo"),
            "sistema_nome": (src.get("sistema") or {}).get("nome"),
            "orgaoJulgador_codigo": (src.get("orgaoJulgador") or {}).get("codigo"),
            "orgaoJulgador_nome": (src.get("orgaoJulgador") or {}).get("nome"),
            "orgaoJulgador_codigoMunicipioIBGE": (src.get("orgaoJulgador") or {}).get("codigoMunicipioIBGE"),
            "dataHoraUltimaAtualizacao": src.get("dataHoraUltimaAtualizacao"),
            "timestamp_indice": src.get("@timestamp"),
        })
        for m in (src.get("movimentos") or []):
            movs.append({
                "numeroProcesso": numero,
                "mov_codigo": m.get("codigo"),
                "mov_nome": m.get("nome"),
                "mov_dataHora": m.get("dataHora"),
                "mov_orgao_codigo": (m.get("orgaoJulgador") or {}).get("codigoOrgao"),
                "mov_orgao_nome": (m.get("orgaoJulgador") or {}).get("nomeOrgao"),
            })
    return pd.DataFrame(procs), pd.DataFrame(movs)

def ensure_schema(sqlite_path=db_path):
    """
    Cria as tabelas base e a nova tabela processos_lista (índice mestre).
    A tabela processos_lista impede reprocessamentos: se o número já está lá,
    o script ignora esse processo em execuções futuras.
    """
    eng = create_engine(f"sqlite:///{sqlite_path}")
    with eng.begin() as con:
        # Tabela principal de processos
        con.execute(text("""
        CREATE TABLE IF NOT EXISTS processos (
            id TEXT,
            tribunal TEXT,
            numeroProcesso TEXT,
            grau TEXT,
            dataAjuizamento TEXT,
            nivelSigilo INTEGER,
            classe_codigo INTEGER,
            classe_nome TEXT,
            formato_codigo INTEGER,
            formato_nome TEXT,
            sistema_codigo INTEGER,
            sistema_nome TEXT,
            orgaoJulgador_codigo INTEGER,
            orgaoJulgador_nome TEXT,
            orgaoJulgador_codigoMunicipioIBGE INTEGER,
            dataHoraUltimaAtualizacao TEXT,
            timestamp_indice TEXT
        )
        """))

        # Movimentos (1:N)
        con.execute(text("""
        CREATE TABLE IF NOT EXISTS movimentos (
            numeroProcesso TEXT,
            mov_codigo INTEGER,
            mov_nome TEXT,
            mov_dataHora TEXT,
            mov_orgao_codigo INTEGER,
            mov_orgao_nome TEXT
        )
        """))

        # NOVA TABELA: índice mestre de processos
        # - numeroProcesso como PRIMARY KEY evita duplicatas
        # - armazena quando entrou e onde foi encontrado pela primeira vez
        con.execute(text("""
        CREATE TABLE IF NOT EXISTS processos_lista (
            numeroProcesso TEXT PRIMARY KEY,
            tribunal_inicial TEXT,
            primeiraInclusao TEXT,
            ultimoUpdate TEXT
        )
        """))

        # Índices úteis (opcionais)
        con.execute(text("CREATE INDEX IF NOT EXISTS ix_proc_numero ON processos (numeroProcesso)"))
        con.execute(text("CREATE INDEX IF NOT EXISTS ix_mov_numero ON movimentos (numeroProcesso)"))

def carrega_lista_existente(sqlite_path=db_path):
    """
    Lê a lista de processos já cadastrados em processos_lista e retorna um set.
    """
    eng = create_engine(f"sqlite:///{sqlite_path}")
    try:
        df_exist = pd.read_sql("SELECT numeroProcesso FROM processos_lista", eng)
        return set(df_exist["numeroProcesso"].astype(str).tolist())
    except Exception:
        return set()

def insere_na_processos_lista(numero, tribunal, sqlite_path=db_path):
    """
    Insere o número na tabela processos_lista (se ainda não existir).
    Como a PRIMARY KEY é numeroProcesso, repetição será ignorada usando UPSERT.
    """
    eng = create_engine(f"sqlite:///{sqlite_path}")
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds").replace('+00:00', 'Z')
    with eng.begin() as con:
        con.execute(text("""
            INSERT INTO processos_lista (numeroProcesso, tribunal_inicial, primeiraInclusao, ultimoUpdate)
            VALUES (:n, :t, :agora, :agora)
            ON CONFLICT(numeroProcesso) DO UPDATE SET ultimoUpdate = excluded.ultimoUpdate
        """), {"n": numero, "t": tribunal, "agora": agora})

def grava_sqlite(dfp, dfm, sqlite_path=db_path):
    eng = create_engine(f"sqlite:///{sqlite_path}")
    with eng.begin() as con:
        if not dfp.empty:
            dfp.to_sql("processos", con, if_exists="append", index=False)
        if not dfm.empty:
            dfm.to_sql("movimentos", con, if_exists="append", index=False)

def limpar_banco_dados(sqlite_path=db_path):
    """
    Limpa completamente o banco de dados, removendo todos os dados das tabelas.
    """
    eng = create_engine(f"sqlite:///{sqlite_path}")
    with eng.begin() as con:
        # Limpar todas as tabelas
        con.execute(text("DELETE FROM processos"))
        con.execute(text("DELETE FROM movimentos"))
        con.execute(text("DELETE FROM processos_lista"))
        print("Banco de dados limpo com sucesso.")

def get_tribunal_endpoint(tribunal_codigo):
    """
    Mapeia código do tribunal para o endpoint correto.
    Retorna None se não encontrar o tribunal.
    """
    if not tribunal_codigo or pd.isna(tribunal_codigo):
        return None
    
    # Normalizar código do tribunal
    tribunal_upper = str(tribunal_codigo).strip().upper()
    
    # Mapeamento direto dos endpoints disponíveis
    if tribunal_upper in endpoints:
        return endpoints[tribunal_upper]
    
    # Mapeamento de variações comuns
    tribunal_variations = {
        "TJ-AC": "TJAC", "TRIBUNAL DE JUSTIÇA DO ACRE": "TJAC", "AC": "TJAC",
        "TJ-AL": "TJAL", "TRIBUNAL DE JUSTIÇA DE ALAGOAS": "TJAL", "AL": "TJAL",
        "TJ-AM": "TJAM", "TRIBUNAL DE JUSTIÇA DO AMAZONAS": "TJAM", "AM": "TJAM",
        "TJ-AP": "TJAP", "TRIBUNAL DE JUSTIÇA DO AMAPÁ": "TJAP", "AP": "TJAP",
        "TJ-BA": "TJBA", "TRIBUNAL DE JUSTIÇA DA BAHIA": "TJBA", "BA": "TJBA",
        "TJ-CE": "TJCE", "TRIBUNAL DE JUSTIÇA DO CEARÁ": "TJCE", "CE": "TJCE",
        "TJ-DF": "TJDFT", "TRIBUNAL DE JUSTIÇA DO DISTRITO FEDERAL": "TJDFT", "DF": "TJDFT",
        "TJ-ES": "TJES", "TRIBUNAL DE JUSTIÇA DO ESPÍRITO SANTO": "TJES", "ES": "TJES",
        "TJ-GO": "TJGO", "TRIBUNAL DE JUSTIÇA DE GOIÁS": "TJGO", "GO": "TJGO",
        "TJ-MA": "TJMA", "TRIBUNAL DE JUSTIÇA DO MARANHÃO": "TJMA", "MA": "TJMA",
        "TJ-MG": "TJMG", "TRIBUNAL DE JUSTIÇA DE MINAS GERAIS": "TJMG", "MG": "TJMG",
        "TJ-MS": "TJMS", "TRIBUNAL DE JUSTIÇA DE MATO GROSSO DO SUL": "TJMS", "MS": "TJMS",
        "TJ-MT": "TJMT", "TRIBUNAL DE JUSTIÇA DE MATO GROSSO": "TJMT", "MT": "TJMT",
        "TJ-PA": "TJPA", "TRIBUNAL DE JUSTIÇA DO PARÁ": "TJPA", "PA": "TJPA",
        "TJ-PB": "TJPB", "TRIBUNAL DE JUSTIÇA DA PARAIBA": "TJPB", "PB": "TJPB",
        "TJ-PE": "TJPE", "TRIBUNAL DE JUSTIÇA DE PERNAMBUCO": "TJPE", "PE": "TJPE",
        "TJ-PI": "TJPI", "TRIBUNAL DE JUSTIÇA DO PIAUÍ": "TJPI", "PI": "TJPI",
        "TJ-PR": "TJPR", "TRIBUNAL DE JUSTIÇA DO PARANÁ": "TJPR", "PR": "TJPR",
        "TJ-RJ": "TJRJ", "TRIBUNAL DE JUSTIÇA DO RIO DE JANEIRO": "TJRJ", "RJ": "TJRJ",
        "TJ-RN": "TJRN", "TRIBUNAL DE JUSTIÇA DO RIO GRANDE DO NORTE": "TJRN", "RN": "TJRN",
        "TJ-RO": "TJRO", "TRIBUNAL DE JUSTIÇA DE RONDÔNIA": "TJRO", "RO": "TJRO",
        "TJ-RR": "TJRR", "TRIBUNAL DE JUSTIÇA DE RORAIMA": "TJRR", "RR": "TJRR",
        "TJ-RS": "TJRS", "TRIBUNAL DE JUSTIÇA DO RIO GRANDE DO SUL": "TJRS", "RS": "TJRS",
        "TJ-SC": "TJSC", "TRIBUNAL DE JUSTIÇA DE SANTA CATARINA": "TJSC", "SC": "TJSC",
        "TJ-SE": "TJSE", "TRIBUNAL DE JUSTIÇA DE SERGIPE": "TJSE", "SE": "TJSE",
        "TJ-SP": "TJSP", "TRIBUNAL DE JUSTIÇA DE SÃO PAULO": "TJSP", "SP": "TJSP",
        "TJ-TO": "TJTO", "TRIBUNAL DE JUSTIÇA DO TOCANTINS": "TJTO", "TO": "TJTO",
    }
    
    # Verificar variações
    if tribunal_upper in tribunal_variations:
        codigo_normalizado = tribunal_variations[tribunal_upper]
        if codigo_normalizado in endpoints:
            return endpoints[codigo_normalizado]
    
    # Se não encontrou, retorna None
    return None

def main():
    try:
        print("Iniciando processamento do banco de dados...")
        
        # Garante o schema (inclui a nova tabela processos_lista)
        ensure_schema(db_path)
        print("Schema do banco verificado")
        
        # Verificar estado atual do banco antes de limpar
        eng = create_engine(f"sqlite:///{db_path}")
        with eng.begin() as con:
            count_before = con.execute(text("SELECT COUNT(*) FROM processos")).fetchone()[0]
            print(f"Processos existentes no banco: {count_before}")
        
        # Limpar o banco de dados completamente
        limpar_banco_dados(db_path)
        print("Banco de dados limpo para nova atualização")

        # Verificar se o arquivo existe
        if not os.path.exists(lista_processos):
            raise FileNotFoundError(f"Arquivo {lista_processos} não encontrado")

        # Ler Excel
        print(f"Lendo arquivo: {lista_processos}")
        df = pd.read_excel(lista_processos)
        
        if df.empty:
            raise ValueError("Arquivo Excel está vazio")
            
        if "numeroProcesso" not in df.columns:
            raise ValueError("O Excel precisa ter a coluna 'numeroProcesso'.")

        print(f"Arquivo lido com {len(df)} linhas")

        # Verificar se tem coluna tribunal
        tem_tribunal = "tribunal" in df.columns
        if tem_tribunal:
            print("[OK] Coluna 'tribunal' encontrada - usando otimizacao por tribunal especifico")
        else:
            print("[AVISO] Coluna 'tribunal' nao encontrada - usando busca em todos os tribunais")

        # Normalizar números
        df["numero_limpo"] = df["numeroProcesso"].map(normaliza_nup)
        df = df[df["numero_limpo"].str.len() >= 15]  # filtro simples
        
        # Se tem tribunal, filtrar apenas processos com tribunal válido
        if tem_tribunal:
            df["endpoint"] = df["tribunal"].map(get_tribunal_endpoint)
            df_validos = df[df["endpoint"].notna()]
            print(f"Processos com tribunal válido: {len(df_validos)} de {len(df)}")
            
            # Mostrar estatísticas dos tribunais encontrados
            if len(df_validos) > 0:
                print("\n[TRIBUNAL] Tribunais encontrados no Excel:")
                tribunal_counts = df_validos["tribunal"].value_counts()
                for tribunal, count in tribunal_counts.items():
                    endpoint = get_tribunal_endpoint(tribunal)
                    status = "[OK]" if endpoint else "[ERRO]"
                    print(f"   {status} {tribunal}: {count} processos")
            
            # Mostrar tribunais não reconhecidos
            df_invalidos = df[df["endpoint"].isna() & df["tribunal"].notna()]
            if len(df_invalidos) > 0:
                print("\n[AVISO] Tribunais nao reconhecidos:")
                invalid_tribunais = df_invalidos["tribunal"].value_counts()
                for tribunal, count in invalid_tribunais.items():
                    print(f"   [ERRO] {tribunal}: {count} processos")
            
            if len(df_validos) == 0:
                print("[AVISO] Nenhum processo com tribunal valido encontrado")
                return
        else:
            df_validos = df
            df_validos["endpoint"] = None

        numeros_excel = df_validos["numero_limpo"].astype(str).unique().tolist()
        print(f"Processando {len(numeros_excel)} números únicos do Excel...")

        total_ok = 0
        total_nao_encontrados = 0
        total_tribunais_nao_encontrados = 0

        # Iterar e consultar cada número no tribunal específico
        for i, numero in enumerate(numeros_excel, 1):
            print(f"[{i}/{len(numeros_excel)}] Processando {numero}...", flush=True)
            encontrado = False
            
            # Obter dados do processo
            processo_row = df_validos[df_validos["numero_limpo"] == numero].iloc[0]
            tribunal_especifico = processo_row.get("tribunal")
            endpoint_especifico = processo_row.get("endpoint")

            if tem_tribunal and endpoint_especifico:
                # OTIMIZACAO: consultar apenas o tribunal específico
                print(f"  [ALVO] Consultando apenas {tribunal_especifico}...")
                try:
                    resp = consulta_por_numero(endpoint_especifico, numero)
                    if resp and not resp.get("_error"):
                        hits = resp.get("hits", {}).get("hits", [])
                        if hits:
                            dfp, dfm = extrai_registros(resp)
                            grava_sqlite(dfp, dfm, db_path)
                            # registra no índice mestre (processos_lista)
                            insere_na_processos_lista(numero, tribunal_especifico, db_path)
                            print(f"[OK] {numero} encontrado em {tribunal_especifico}", flush=True)
                            total_ok += 1
                            encontrado = True
                        else:
                            print(f"[AVISO] {numero} nao encontrado em {tribunal_especifico}", flush=True)
                    else:
                        print(f"[AVISO] {numero} erro em {tribunal_especifico}: {resp}", flush=True)
                except Exception as e:
                    print(f"[AVISO] {numero} erro em {tribunal_especifico}: {str(e)}", flush=True)
                    
                time.sleep(sleep_between)
                
                if not encontrado:
                    total_tribunais_nao_encontrados += 1
                    
            else:
                # Fallback: buscar em todos os tribunais (comportamento antigo)
                print(f"  [BUSCA] Buscando em todos os tribunais...")
                for trib, url in endpoints.items():
                    try:
                        resp = consulta_por_numero(url, numero)
                        if resp and not resp.get("_error"):
                            hits = resp.get("hits", {}).get("hits", [])
                            if hits:
                                dfp, dfm = extrai_registros(resp)
                                grava_sqlite(dfp, dfm, db_path)
                                # registra no índice mestre (processos_lista)
                                insere_na_processos_lista(numero, trib, db_path)
                                print(f"[OK] {numero} encontrado em {trib}", flush=True)
                                total_ok += 1
                                encontrado = True
                                break
                        else:
                            # loga erro, segue para próximo tribunal
                            print(f"[AVISO] {numero} erro em {trib}: {resp}", flush=True)
                    except Exception as e:
                        print(f"[AVISO] {numero} erro em {trib}: {str(e)}", flush=True)
                        
                    time.sleep(sleep_between)

                if not encontrado:
                    print(f"[ERRO] {numero} nao encontrado", flush=True)
                    total_nao_encontrados += 1

        # Verificar estado final do banco
        eng = create_engine(f"sqlite:///{db_path}")
        with eng.begin() as con:
            count_after = con.execute(text("SELECT COUNT(*) FROM processos")).fetchone()[0]
            count_movimentos = con.execute(text("SELECT COUNT(*) FROM movimentos")).fetchone()[0]
        
        print(f"\nCONCLUIDO!", flush=True)
        print(f"Processos encontrados: {total_ok}", flush=True)
        if tem_tribunal:
            print(f"Processos não encontrados no tribunal específico: {total_tribunais_nao_encontrados}", flush=True)
        else:
            print(f"Processos não encontrados: {total_nao_encontrados}", flush=True)
        print(f"Banco: {db_path}", flush=True)
        print(f"Total de processos no banco: {count_after}", flush=True)
        print(f"Total de movimentos no banco: {count_movimentos}", flush=True)
        
        
        if count_after == 0:
            print("ATENCAO: Banco ficou vazio! Verifique:")
            print("   - Conexão com a internet")
            print("   - Disponibilidade da API DataJud")
            print("   - Se os números na planilha são válidos")
            if tem_tribunal:
                print("   - Se os códigos de tribunal na planilha estão corretos")
        
    except Exception as e:
        print(f"ERRO FATAL: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()
