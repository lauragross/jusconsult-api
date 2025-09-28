# app.py
import os
import pandas as pd
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flasgger import Swagger, swag_from
from werkzeug.utils import secure_filename

from utils import get_conn, rows_to_dicts, get_pagination_params, DB_PATH
from dataframe_utils import get_auxiliary_dataframes, invalidate_dataframe_cache, update_filter_lists, get_unique_categories, get_unique_tribunals

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
CORS(app)

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "DataJud Processos API",
        "description": "API para leitura das tabelas do SQLite datajud_processos.db",
        "version": "1.0.0",
    },
    "basePath": "/",
}
swagger = Swagger(app, template=swagger_template)

@app.route("/processos", methods=["GET"])
@swag_from({
    "tags": ["processos"],
    "parameters": [
        {"name": "numero", "in": "query", "type": "string", "required": False,
         "description": "Filtro por numeroProcesso (exato)"},
        {"name": "tribunal", "in": "query", "type": "string", "required": False,
         "description": "Filtro por tribunal (ex: TJRJ, TJSP, ...)"},
        {"name": "categoria", "in": "query", "type": "string", "required": False,
         "description": "Filtro por categoria"},
        {"name": "limit", "in": "query", "type": "integer", "required": False, "default": 10000},
        {"name": "offset", "in": "query", "type": "integer", "required": False, "default": 0},
    ],
    "responses": {
        200: {"description": "Lista de processos com informações auxiliares", "schema": {"type": "object"}}
    }
})
def get_processos():
    """
    Retorna lista de processos com informações auxiliares:
    - numeroProcesso
    - tribunal
    - categoria (do Excel)
    - sistema_nome
    - dataHoraUltimaAtualizacao
    - nome do último movimento
    ---
    """
    try:
        # Obter parâmetros de filtro
        numero = request.args.get("numero")
        tribunal = request.args.get("tribunal")
        categoria = request.args.get("categoria")
        limit, offset = get_pagination_params(request)

        # Obter dataframe auxiliar
        dataframes = get_auxiliary_dataframes()
        df_final = dataframes['final']

        # Aplicar filtros
        if numero:
            df_final = df_final[df_final['numeroProcesso'] == numero]
        if tribunal:
            df_final = df_final[df_final['tribunal'] == tribunal]
        if categoria:
            df_final = df_final[df_final['categoria'] == categoria]

        # Ordenar por numeroProcesso
        df_final = df_final.sort_values('numeroProcesso')

        # Aplicar paginação
        total = len(df_final)
        df_paginated = df_final.iloc[offset:offset + limit]

        # Converter para formato JSON
        data = []
        for _, row in df_paginated.iterrows():
            data.append({
                "numeroProcesso": row['numeroProcesso'],
                "tribunal": row['tribunal'],
                "categoria": row['categoria'] if pd.notna(row['categoria']) else None,
                "sistema_nome": row['sistema_nome'],
                "dataHoraUltimaAtualizacao": row['dataHoraUltimaAtualizacao'],
                "ultimoMovimento": row['mov_nome'] if pd.notna(row['mov_nome']) else None
            })

        return jsonify({
            "data": data,
            "pagination": {"limit": limit, "offset": offset, "total": total}
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/movimentos/<numero>", methods=["GET"])
@swag_from({
    "tags": ["movimentos"],
    "parameters": [
        {
            "name": "limit",
            "in": "query",
            "type": "integer",
            "required": False,
            "default": 10000,
            "description": "Número máximo de linhas a retornar"
        },
        {
            "name": "offset",
            "in": "query",
            "type": "integer",
            "required": False,
            "default": 0,
            "description": "Número de linhas a pular (para paginação)"
        },
    ],
    "responses": {
        200: {
            "description": "Lista de movimentos de um processo",
            "schema": {"type": "object"}
        }
    }
})
def get_movimentos(numero):
    """
    Retorna linhas da tabela **movimentos** de um processo específico.
    ---
    """
    limit, offset = get_pagination_params(request)

    sql = """
        SELECT *
        FROM movimentos
        WHERE numeroProcesso = ?
        ORDER BY mov_dataHora DESC
        LIMIT ? OFFSET ?
    """
    params = [numero, limit, offset]

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) AS total FROM movimentos WHERE numeroProcesso = ?",
            [numero]
        ).fetchone()["total"]

    return jsonify({
        "data": rows_to_dicts(rows),
        "pagination": {"limit": limit, "offset": offset, "total": total}
    })


@app.route("/processos-lista", methods=["GET"])
@swag_from({
    "tags": ["processos_lista"],
    "parameters": [
        {"name": "numero", "in": "query", "type": "string", "required": False,
         "description": "Filtro por numeroProcesso (exato)"},
        {"name": "limit", "in": "query", "type": "integer", "required": False, "default": 10000},
        {"name": "offset", "in": "query", "type": "integer", "required": False, "default": 0},
    ],
    "responses": {
        200: {"description": "Lista mestre de processos", "schema": {"type": "object"}}
    }
})
def get_processos_lista():
    """
    Retorna linhas da tabela **processos_lista**.
    ---
    """
    numero = request.args.get("numero")
    limit, offset = get_pagination_params(request)

    wheres, params = [], []
    if numero:
        wheres.append("numeroProcesso = ?")
        params.append(numero)

    where_sql = f"WHERE {' AND '.join(wheres)}" if wheres else ""
    sql = f"""
        SELECT *
        FROM processos_lista
        {where_sql}
        ORDER BY primeiraInclusao DESC
        LIMIT ? OFFSET ?
    """
    params_with_pagination = params + [limit, offset]

    with get_conn() as conn:
        rows = conn.execute(sql, params_with_pagination).fetchall()
        total_sql = f"SELECT COUNT(*) AS total FROM processos_lista {where_sql}"
        total = conn.execute(total_sql, params).fetchone()["total"] if params else \
                conn.execute("SELECT COUNT(*) AS total FROM processos_lista").fetchone()["total"]

    # Converter para formato esperado pelo frontend
    processos = []
    for row in rows_to_dicts(rows):
        processos.append({
            "numero": row.get("numeroProcesso"),
            "tribunal": row.get("tribunal"),
            "grau": row.get("grau"),
            "classe": row.get("classe"),
            "primeiraInclusao": row.get("primeiraInclusao"),
            "ultimaConsulta": row.get("ultimaConsulta")
        })

    return jsonify(processos)


@app.route("/health", methods=["GET"])
def health_check():
    """
    Endpoint de verificação de saúde do servidor.
    ---
    """
    return jsonify({"status": "ok", "message": "Servidor funcionando"})

@app.route("/tribunais", methods=["GET"])
@swag_from({
    "tags": ["tribunais"],
    "responses": {
        200: {"description": "Lista de tribunais únicos", "schema": {"type": "array"}}
    }
})
def get_tribunais():
    """
    Retorna lista de tribunais únicos disponíveis na base.
    Garante que não há duplicatas na lista.
    ---
    """
    try:
        # Usar a função atualizada que garante listas únicas
        tribunais = get_unique_tribunals(DB_PATH)
        
        # Log para debug
        print(f"🔍 Endpoint /tribunais retornando: {tribunais}")
        
        # Criar resposta com headers para evitar cache
        response = jsonify(tribunais)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response
    except Exception as e:
        print(f"Erro no endpoint /tribunais: {str(e)}")
        return jsonify({"error": f"Erro ao buscar tribunais: {str(e)}"}), 500


@app.route("/categorias", methods=["GET"])
@swag_from({
    "tags": ["categorias"],
    "responses": {
        200: {"description": "Lista de categorias únicas do dataframe auxiliar", "schema": {"type": "array"}}
    }
})
def get_categorias():
    """
    Retorna lista de categorias únicas disponíveis no dataframe auxiliar.
    Garante que não há duplicatas na lista.
    ---
    """
    try:
        # Forçar invalidação do cache antes de buscar categorias
        invalidate_dataframe_cache()
        
        # Usar a função atualizada que garante listas únicas
        categorias = get_unique_categories(DB_PATH, 'processos.xlsx')
        
        # Log para debug
        print(f"🔍 Endpoint /categorias retornando: {categorias}")
        
        # Criar resposta com headers para evitar cache
        response = jsonify(categorias)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response
    except Exception as e:
        print(f"Erro no endpoint /categorias: {str(e)}")
        return jsonify({"error": f"Erro ao buscar categorias: {str(e)}"}), 500


@app.route("/atualizacoes", methods=["GET"])
@swag_from({
    "tags": ["atualizacoes"],
    "responses": {
        200: {"description": "Lista de processos com suas últimas atualizações", "schema": {"type": "object"}}
    }
})
def get_atualizacoes():
    """
    Retorna processos agrupados por período de atualização com última movimentação.
    ---
    """
    try:
        with get_conn() as conn:
            # Query simplificada para evitar problemas de compatibilidade
            sql_processos = """
                SELECT *
                FROM processos 
                ORDER BY dataHoraUltimaAtualizacao DESC
            """
            processos = conn.execute(sql_processos).fetchall()
            
            # Buscar última movimentação para cada processo
            processos_com_movimentacao = []
            for processo in rows_to_dicts(processos):
                numero = processo["numeroProcesso"]
                
                # Buscar última movimentação para este processo
                sql_movimento = """
                    SELECT *
                    FROM movimentos 
                    WHERE numeroProcesso = ? 
                    ORDER BY mov_dataHora DESC 
                    LIMIT 1
                """
                movimento = conn.execute(sql_movimento, (numero,)).fetchone()
                
                if movimento:
                    movimento_dict = dict(movimento)
                    processo["ultima_movimentacao_data"] = movimento_dict.get("mov_dataHora")
                    processo["ultima_movimentacao_tipo"] = movimento_dict.get("mov_tipo") or movimento_dict.get("tipo")
                    processo["ultima_movimentacao_descricao"] = movimento_dict.get("mov_descricao") or movimento_dict.get("descricao")
                else:
                    processo["ultima_movimentacao_data"] = None
                    processo["ultima_movimentacao_tipo"] = None
                    processo["ultima_movimentacao_descricao"] = None
                
                processos_com_movimentacao.append(processo)
        
        # Agrupar por período
        from datetime import datetime, timedelta
        now = datetime.now()
        
        categorias = {
            "ultimas_24h": [],
            "ultimos_7_dias": [],
            "ultimo_mes": [],
            "ultimo_ano": [],
            "mais_de_um_ano": []
        }
        
        for row in processos_com_movimentacao:
            data_atualizacao = row.get("dataHoraUltimaAtualizacao")
            if not data_atualizacao:
                categorias["mais_de_um_ano"].append(row)
                continue
                
            try:
                # Tentar diferentes formatos de data
                data = None
                date_string = str(data_atualizacao)
                
                # Tentar formato ISO
                if 'T' in date_string:
                    if date_string.endswith('Z'):
                        date_string = date_string.replace('Z', '+00:00')
                    data = datetime.fromisoformat(date_string)
                else:
                    # Tentar outros formatos comuns
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y %H:%M:%S']:
                        try:
                            data = datetime.strptime(date_string, fmt)
                            break
                        except:
                            continue
                
                if data is None:
                    categorias["mais_de_um_ano"].append(row)
                    continue
                
                # Remover timezone se existir
                if data.tzinfo is not None:
                    data = data.replace(tzinfo=None)
                
                diff = now - data
                
                if diff <= timedelta(hours=24):
                    categorias["ultimas_24h"].append(row)
                elif diff <= timedelta(days=7):
                    categorias["ultimos_7_dias"].append(row)
                elif diff <= timedelta(days=30):
                    categorias["ultimo_mes"].append(row)
                elif diff <= timedelta(days=365):
                    categorias["ultimo_ano"].append(row)
                else:
                    categorias["mais_de_um_ano"].append(row)
            except Exception as e:
                # Se houver qualquer erro no parsing da data, colocar na categoria mais antiga
                categorias["mais_de_um_ano"].append(row)
        
        return jsonify(categorias)
        
    except Exception as e:
        return jsonify({"error": f"Erro interno: {str(e)}"}), 500


@app.route("/atualizacoes-dataframe", methods=["GET"])
@swag_from({
    "tags": ["atualizacoes"],
    "parameters": [
        {"name": "tribunal", "in": "query", "type": "string", "required": False,
         "description": "Filtro por tribunal (ex: TJRJ, TJSP, ...)"},
        {"name": "categoria", "in": "query", "type": "string", "required": False,
         "description": "Filtro por categoria"},
    ],
    "responses": {
        200: {"description": "Lista de processos com informações do dataframe auxiliar agrupados por período", "schema": {"type": "object"}}
    }
})
def get_atualizacoes_dataframe():
    """
    Retorna processos do dataframe auxiliar agrupados por período de atualização.
    Inclui: numeroProcesso, tribunal, categoria, sistema_nome, dataHoraUltimaAtualizacao, nome do último movimento
    ---
    """
    try:
        # Obter parâmetros de filtro
        tribunal = request.args.get("tribunal")
        categoria = request.args.get("categoria")

        # Obter dataframe auxiliar
        dataframes = get_auxiliary_dataframes()
        df_final = dataframes['final']

        # Aplicar filtros
        if tribunal:
            df_final = df_final[df_final['tribunal'] == tribunal]
        if categoria:
            df_final = df_final[df_final['categoria'] == categoria]

        # Converter para lista de dicionários
        processos = []
        for _, row in df_final.iterrows():
            processos.append({
                "numeroProcesso": row['numeroProcesso'],
                "tribunal": row['tribunal'],
                "categoria": row['categoria'] if pd.notna(row['categoria']) else None,
                "sistema_nome": row['sistema_nome'],
                "dataHoraUltimaAtualizacao": row['dataHoraUltimaAtualizacao'],
                "ultimoMovimento": row['mov_nome'] if pd.notna(row['mov_nome']) else None
            })

        # Agrupar por período
        from datetime import datetime, timedelta
        now = datetime.now()
        
        categorias = {
            "ultimas_24h": [],
            "ultimos_7_dias": [],
            "ultimo_mes": [],
            "ultimo_ano": [],
            "mais_de_um_ano": []
        }
        
        for processo in processos:
            data_atualizacao = processo.get("dataHoraUltimaAtualizacao")
            if not data_atualizacao:
                categorias["mais_de_um_ano"].append(processo)
                continue
                
            try:
                # Tentar diferentes formatos de data
                data = None
                date_string = str(data_atualizacao)
                
                # Tentar formato ISO
                if 'T' in date_string:
                    if date_string.endswith('Z'):
                        date_string = date_string.replace('Z', '+00:00')
                    data = datetime.fromisoformat(date_string)
                else:
                    # Tentar outros formatos comuns
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y %H:%M:%S']:
                        try:
                            data = datetime.strptime(date_string, fmt)
                            break
                        except:
                            continue
                
                if data is None:
                    categorias["mais_de_um_ano"].append(processo)
                    continue
                
                # Remover timezone se existir
                if data.tzinfo is not None:
                    data = data.replace(tzinfo=None)
                
                diff = now - data
                
                if diff <= timedelta(hours=24):
                    categorias["ultimas_24h"].append(processo)
                elif diff <= timedelta(days=7):
                    categorias["ultimos_7_dias"].append(processo)
                elif diff <= timedelta(days=30):
                    categorias["ultimo_mes"].append(processo)
                elif diff <= timedelta(days=365):
                    categorias["ultimo_ano"].append(processo)
                else:
                    categorias["mais_de_um_ano"].append(processo)
            except Exception as e:
                # Se houver qualquer erro no parsing da data, colocar na categoria mais antiga
                categorias["mais_de_um_ano"].append(processo)
        
        return jsonify(categorias)
        
    except Exception as e:
        return jsonify({"error": f"Erro interno: {str(e)}"}), 500


@app.route("/processo/<numero>", methods=["GET"])
@swag_from({
    "tags": ["agregado"],
    "parameters": [
        {"name": "numero", "in": "path", "type": "string", "required": True,
         "description": "numeroProcesso (exato, sem máscara)"},
    ],
    "responses": {
        200: {"description": "Objeto agregado", "schema": {"type": "object"}},
        404: {"description": "Processo não encontrado"}
    }
})
def get_processo_agregado(numero):
    """
    Retorna **um** processo agregado:
    - processos (capa),
    - movimentos (lista),
    - processos_lista (registro mestre).
    ---
    """
    with get_conn() as conn:
        proc = conn.execute(
            "SELECT * FROM processos WHERE numeroProcesso = ? "
            "ORDER BY dataHoraUltimaAtualizacao DESC LIMIT 1",
            (numero,)
        ).fetchone()

        # Buscar as últimas 100 movimentações
        movs = conn.execute(
            "SELECT * FROM movimentos WHERE numeroProcesso = ? ORDER BY mov_dataHora DESC LIMIT 100",
            (numero,)
        ).fetchall()
        
        # Contar total de movimentos
        mov_count = conn.execute(
            "SELECT COUNT(*) FROM movimentos WHERE numeroProcesso = ?",
            (numero,)
        ).fetchone()[0]

        lista = conn.execute(
            "SELECT * FROM processos_lista WHERE numeroProcesso = ?",
            (numero,)
        ).fetchone()

    if not proc and not lista and mov_count == 0:
        return jsonify({"error": "Processo não encontrado"}), 404

    return jsonify({
        "processo": dict(proc) if proc else None,
        "movimentos": rows_to_dicts(movs),  # Retorna as últimas 100 movimentações
        "total_movimentos": mov_count,  # Total de movimentos no processo
        "processos_lista": dict(lista) if lista else None
    })




@app.route("/upload-processos", methods=["POST"])
@swag_from({
    "tags": ["upload"],
    "parameters": [
        {
            "name": "file",
            "in": "formData",
            "type": "file",
            "required": True,
            "description": "Arquivo Excel com lista de processos"
        }
    ],
    "responses": {
        200: {"description": "Upload realizado com sucesso"},
        400: {"description": "Arquivo inválido"}
    }
})
def upload_processos():
    """
    Faz upload de um arquivo Excel temporário para validação.
    ---
    """
    try:
        if 'file' not in request.files:
            return jsonify({"error": "Nenhum arquivo enviado"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "Nenhum arquivo selecionado"}), 400
        
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({"error": "Arquivo deve ser Excel (.xlsx ou .xls)"}), 400
        
        # Salvar o arquivo temporariamente
        temp_filename = 'processos_temp.xlsx'
        file.save(temp_filename)
        
        # Ler o arquivo para validar e contar registros
        df = pd.read_excel(temp_filename)
        
        # Verificar se tem dados
        if df.empty:
            return jsonify({"error": "Arquivo Excel está vazio"}), 400
        
        # Verificar se tem a coluna necessária
        if 'numeroProcesso' not in df.columns:
            return jsonify({"error": "Arquivo deve conter a coluna 'numeroProcesso'"}), 400
        
        total_registros = len(df)
        
        return jsonify({
            "message": "Arquivo validado com sucesso",
            "total": total_registros
        })
        
    except Exception as e:
        return jsonify({"error": f"Erro no upload: {str(e)}"}), 500


@app.route("/template-excel", methods=["GET"])
@swag_from({
    "tags": ["template"],
    "responses": {
        200: {"description": "Template Excel para upload de processos"}
    }
})
def download_template():
    """
    Retorna o arquivo processos.xlsx atual como template.
    ---
    """
    try:
        # Caminho para o arquivo processos.xlsx
        excel_path = 'processos.xlsx'
        
        if not os.path.exists(excel_path):
            return jsonify({"error": "Arquivo processos.xlsx não encontrado"}), 404
        
        return send_file(
            excel_path,
            as_attachment=True,
            download_name='processos.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        return jsonify({"error": f"Erro ao baixar template: {str(e)}"}), 500


@app.route("/confirm-replace", methods=["POST"])
@swag_from({
    "tags": ["confirm"],
    "responses": {
        200: {"description": "Lista substituída com sucesso"},
        404: {"description": "Arquivo temporário não encontrado"}
    }
})
def confirm_replace():
    """
    Confirma a substituição do arquivo processos.xlsx pelo arquivo temporário.
    ---
    """
    try:
        temp_filename = 'processos_temp.xlsx'
        
        if not os.path.exists(temp_filename):
            return jsonify({"error": "Arquivo temporário não encontrado"}), 404
        
        # Substituir o arquivo original pelo temporário
        import shutil
        shutil.move(temp_filename, 'processos.xlsx')
        
        return jsonify({
            "message": "Lista de processos substituída com sucesso"
        })
        
    except Exception as e:
        return jsonify({"error": f"Erro ao confirmar substituição: {str(e)}"}), 500


@app.route("/update-database", methods=["POST"])
@swag_from({
    "tags": ["database"],
    "responses": {
        200: {"description": "Banco de dados atualizado com sucesso"},
        500: {"description": "Erro ao atualizar banco"}
    }
})
def update_database():
    """
    Atualiza o banco de dados executando o database.py com a nova lista.
    ---
    """
    try:
        import subprocess
        import sys
        
        print(f"Executando database.py em: {os.getcwd()}")
        print(f"Arquivo processos.xlsx existe: {os.path.exists('processos.xlsx')}")
        
        # Verificar se o arquivo processos.xlsx existe
        if not os.path.exists('processos.xlsx'):
            return jsonify({
                "error": "Arquivo processos.xlsx não encontrado. Faça o upload primeiro."
            }), 400
        
        # Executar o database.py
        result = subprocess.run([
            sys.executable, 'database.py'
        ], capture_output=True, text=True, cwd=os.getcwd(), timeout=300)  # 5 minutos timeout
        
        print(f"Return code: {result.returncode}")
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        
        if result.returncode != 0:
            return jsonify({
                "error": f"Erro ao executar database.py (código {result.returncode}): {result.stderr}",
                "stdout": result.stdout
            }), 500
        
        # Invalidar cache dos dataframes auxiliares após atualização bem-sucedida
        try:
            invalidate_dataframe_cache()
            print("Cache dos dataframes auxiliares invalidado após atualização do banco")
            
            # Atualizar listas de filtros (categorias e tribunais)
            print("Atualizando listas de filtros...")
            filter_lists = update_filter_lists(DB_PATH, 'processos.xlsx')
            print(f"Listas atualizadas: {len(filter_lists['categorias'])} categorias, {len(filter_lists['tribunais'])} tribunais")
            
        except Exception as cache_error:
            print(f"Erro ao invalidar cache: {str(cache_error)}")
        
        # Parsear a saída para extrair estatísticas
        output = result.stdout
        processados = 0
        encontrados = 0
        nao_encontrados = 0
        
        # Buscar padrões na saída
        import re
        if "Processos encontrados:" in output:
            match = re.search(r"Processos encontrados: (\d+)", output)
            if match:
                processados = int(match.group(1))
        
        # Contar processos encontrados e não encontrados
        encontrados = output.count("[OK]")
        nao_encontrados = output.count("[ERRO]")
        
        return jsonify({
            "message": "Banco de dados atualizado com sucesso",
            "processados": processados,
            "encontrados": encontrados,
            "nao_encontrados": nao_encontrados,
            "output": output
        })
        
    except subprocess.TimeoutExpired:
        return jsonify({
            "error": "Timeout: O processamento demorou mais de 5 minutos"
        }), 500
    except Exception as e:
        print(f"Erro no update_database: {str(e)}")
        return jsonify({
            "error": f"Erro ao atualizar banco de dados: {str(e)}"
        }), 500


@app.route("/update-database-stream", methods=["POST"])
def update_database_stream():
    """
    Atualiza o banco de dados com streaming de progresso em tempo real.
    ---
    """
    try:
        from flask import Response
        import subprocess
        import sys
        import json
        import re
        
        print(f"Iniciando update-database-stream em: {os.getcwd()}")
        print(f"📁 Arquivo processos.xlsx existe: {os.path.exists('processos.xlsx')}")
        
        # Verificar se o arquivo processos.xlsx existe
        if not os.path.exists('processos.xlsx'):
            return jsonify({
                "error": "Arquivo processos.xlsx não encontrado. Faça o upload primeiro."
            }), 400
        
        def generate():
            try:
                # Enviar mensagem inicial
                yield f"data: {json.dumps({'type': 'log', 'message': 'Iniciando atualização do banco de dados...', 'level': 'info'})}\n\n"
                
                # Verificar se o arquivo tem dados
                try:
                    df = pd.read_excel('processos.xlsx')
                    # mantém apenas linhas onde numeroProcesso não é vazio
                    df = df[df["numeroProcesso"].notna() & (df["numeroProcesso"] != "")]
                    if df.empty:
                        yield f"data: {json.dumps({'type': 'log', 'message': 'Arquivo Excel está vazio', 'level': 'error'})}\n\n"
                        return
                    if 'numeroProcesso' not in df.columns:
                        yield f"data: {json.dumps({'type': 'log', 'message': 'Arquivo Excel não tem coluna numeroProcesso', 'level': 'error'})}\n\n"
                        return
                    yield f"data: {json.dumps({'type': 'log', 'message': f'Arquivo Excel tem {len(df)} processos', 'level': 'info'})}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'log', 'message': f'Erro ao ler Excel: {str(e)}', 'level': 'error'})}\n\n"
                    return
                
                # Executar o database.py com streaming
                yield f"data: {json.dumps({'type': 'log', 'message': 'Executando database.py...', 'level': 'info'})}\n\n"
                
                process = subprocess.Popen([
                    sys.executable, 'database.py'
                ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                   universal_newlines=True, cwd=os.getcwd())
                
                # Variáveis para rastrear progresso
                tribunal_stats = {}
                not_found_processes = []
                total_processed = 0
                
                # Ler saída linha por linha
                for line in iter(process.stdout.readline, ''):
                    if line:
                        line = line.strip()
                        
                        # Parsear diferentes tipos de mensagem
                        if "Processando" in line and "[" in line and "]" in line:
                            # Extrair número do processo atual
                            match = re.search(r'\[(\d+)/(\d+)\]', line)
                            if match:
                                current = int(match.group(1))
                                total = int(match.group(2))
                                total_processed = total
                                yield f"data: {json.dumps({'type': 'progress', 'current': current, 'total': total})}\n\n"
                        
                        elif "[OK]" in line and "encontrado em" in line:
                            # Processo encontrado
                            match = re.search(r'\[OK\]\s*([^\s]+)\s+encontrado em (\w+)', line)
                            if match:
                                processo = match.group(1)
                                tribunal = match.group(2)
                                tribunal_stats[tribunal] = tribunal_stats.get(tribunal, 0) + 1
                                yield f"data: {json.dumps({'type': 'log', 'message': line, 'level': 'success'})}\n\n"
                                yield f"data: {json.dumps({'type': 'tribunal', 'tribunal': tribunal, 'count': tribunal_stats[tribunal]})}\n\n"
                        
                        elif "[ERRO]" in line and "não encontrado" in line:
                            # Processo não encontrado
                            match = re.search(r'\[ERRO\]\s*([^\s]+)\s+não encontrado', line)
                            if match:
                                processo = match.group(1)
                                not_found_processes.append(processo)
                                yield f"data: {json.dumps({'type': 'log', 'message': line, 'level': 'error'})}\n\n"
                                yield f"data: {json.dumps({'type': 'notFound', 'processo': processo})}\n\n"
                        
                        elif "[AVISO]" in line:
                            # Aviso
                            yield f"data: {json.dumps({'type': 'log', 'message': line, 'level': 'warning'})}\n\n"
                        
                        else:
                            # Log geral
                            yield f"data: {json.dumps({'type': 'log', 'message': line, 'level': 'info'})}\n\n"
                
                # Aguardar o processo terminar
                return_code = process.wait()
                yield f"data: {json.dumps({'type': 'log', 'message': f'Processo finalizado com código: {return_code}', 'level': 'info'})}\n\n"
                
                # Invalidar cache dos dataframes auxiliares se a atualização foi bem-sucedida
                if return_code == 0:
                    try:
                        invalidate_dataframe_cache()
                        yield f"data: {json.dumps({'type': 'log', 'message': 'Cache dos dataframes auxiliares invalidado', 'level': 'info'})}\n\n"
                        
                        # Atualizar listas de filtros (categorias e tribunais)
                        yield f"data: {json.dumps({'type': 'log', 'message': 'Atualizando listas de filtros...', 'level': 'info'})}\n\n"
                        filter_lists = update_filter_lists(DB_PATH, 'processos.xlsx')
                        
                        # Enviar informações sobre as listas atualizadas
                        yield f"data: {json.dumps({'type': 'filter_update', 'categorias': filter_lists['categorias'], 'tribunais': filter_lists['tribunais']})}\n\n"
                        message = f"Listas atualizadas: {len(filter_lists['categorias'])} categorias, {len(filter_lists['tribunais'])} tribunais"
                        yield f"data: {json.dumps({'type': 'log', 'message': message, 'level': 'success'})}\n\n"
                        
                    except Exception as cache_error:
                        yield f"data: {json.dumps({'type': 'log', 'message': f'Erro ao invalidar cache: {str(cache_error)}', 'level': 'warning'})}\n\n"
                
                # Enviar estatísticas finais
                yield f"data: {json.dumps({'type': 'log', 'message': 'Atualização concluída!', 'level': 'success'})}\n\n"
                
                total_found = sum(tribunal_stats.values())
                yield f"data: {json.dumps({'type': 'log', 'message': f'Total encontrado: {total_found} processos', 'level': 'info'})}\n\n"
                yield f"data: {json.dumps({'type': 'log', 'message': f'Total não encontrado: {len(not_found_processes)} processos', 'level': 'info'})}\n\n"
                
                # Enviar lista de não encontrados
                for processo in not_found_processes:
                    yield f"data: {json.dumps({'type': 'notFound', 'processo': processo})}\n\n"
                
                # Enviar estatísticas por tribunal
                for tribunal, count in tribunal_stats.items():
                    yield f"data: {json.dumps({'type': 'tribunal', 'tribunal': tribunal, 'count': count})}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'type': 'log', 'message': f'Erro durante execução: {str(e)}', 'level': 'error'})}\n\n"
                import traceback
                yield f"data: {json.dumps({'type': 'log', 'message': f'Traceback: {traceback.format_exc()}', 'level': 'error'})}\n\n"
        
        return Response(generate(), mimetype='text/event-stream')
        
    except Exception as e:
        print(f"Erro no update_database_stream: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            "error": f"Erro ao iniciar atualização: {str(e)}"
        }), 500


@app.route("/test-database", methods=["GET"])
def test_database():
    """
    Endpoint de teste para verificar se o database.py está funcionando.
    ---
    """
    try:
        import subprocess
        import sys
        
        print(f"Testando database.py em: {os.getcwd()}")
        print(f"Arquivo processos.xlsx existe: {os.path.exists('processos.xlsx')}")
        
        # Verificar se o arquivo processos.xlsx existe
        if not os.path.exists('processos.xlsx'):
            return jsonify({
                "error": "Arquivo processos.xlsx não encontrado",
                "files_in_directory": os.listdir('.')
            }), 400
        
        # Verificar conteúdo do arquivo Excel
        try:
            df = pd.read_excel('processos.xlsx')
            # mantém apenas linhas onde numeroProcesso não é vazio
            df = df[df["numeroProcesso"].notna() & (df["numeroProcesso"] != "")]
            excel_info = {
                "total_rows": len(df),
                "columns": df.columns.tolist(),
                "has_numeroProcesso": 'numeroProcesso' in df.columns
            }
            if 'numeroProcesso' in df.columns:
                excel_info["sample_numbers"] = df['numeroProcesso'].head(3).tolist()
        except Exception as e:
            excel_info = {"error": str(e)}
        
        # Executar o database.py com timeout menor para teste
        result = subprocess.run([
            sys.executable, 'database.py'
        ], capture_output=True, text=True, cwd=os.getcwd(), timeout=60)  # 1 minuto timeout
        
        return jsonify({
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0,
            "excel_info": excel_info,
            "working_directory": os.getcwd()
        })
        
    except subprocess.TimeoutExpired:
        return jsonify({
            "error": "Timeout: O teste demorou mais de 1 minuto",
            "return_code": -1
        }), 500
    except Exception as e:
        return jsonify({
            "error": f"Erro no teste: {str(e)}",
            "return_code": -1
        }), 500


@app.route("/clear-database", methods=["POST"])
@swag_from({
    "tags": ["database"],
    "responses": {
        200: {"description": "Banco de dados limpo com sucesso"},
        500: {"description": "Erro ao limpar banco"}
    }
})
def clear_database():
    """
    Limpa completamente o banco de dados (remove todos os dados).
    Use com cuidado!
    ---
    """
    try:
        from database import limpar_banco_dados
        limpar_banco_dados()
        
        return jsonify({
            "message": "Banco de dados limpo com sucesso",
            "warning": "Todos os dados foram removidos!"
        })
        
    except Exception as e:
        return jsonify({
            "error": f"Erro ao limpar banco: {str(e)}"
        }), 500


@app.route("/update-filter-lists", methods=["POST"])
@swag_from({
    "tags": ["filters"],
    "responses": {
        200: {"description": "Listas de filtros atualizadas com sucesso"},
        500: {"description": "Erro ao atualizar listas"}
    }
})
def update_filter_lists_endpoint():
    """
    Força a atualização das listas de categorias e tribunais.
    Útil para garantir que os filtros estejam atualizados após mudanças no banco.
    ---
    """
    try:
        # Invalidar cache primeiro
        invalidate_dataframe_cache()
        
        # Atualizar listas de filtros
        filter_lists = update_filter_lists(DB_PATH, 'processos.xlsx')
        
        return jsonify({
            "message": "Listas de filtros atualizadas com sucesso",
            "categorias_count": len(filter_lists['categorias']),
            "tribunais_count": len(filter_lists['tribunais']),
            "categorias": filter_lists['categorias'],
            "tribunais": filter_lists['tribunais']
        })
        
    except Exception as e:
        return jsonify({
            "error": f"Erro ao atualizar listas de filtros: {str(e)}"
        }), 500

@app.route("/test-categorias", methods=["GET"])
def test_categorias():
    """
    Endpoint de teste para verificar as categorias.
    ---
    """
    try:
        print("Testando função get_unique_categories...")
        categorias = get_unique_categories(DB_PATH, 'processos.xlsx')
        
        return jsonify({
            "success": True,
            "categorias": categorias,
            "total": len(categorias),
            "message": "Teste de categorias executado com sucesso"
        })
    except Exception as e:
        print(f"Erro no teste de categorias: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@app.route("/force-update-filters", methods=["POST"])
def force_update_filters():
    """
    Força a atualização das listas de filtros.
    ---
    """
    try:
        print("Forçando atualização das listas de filtros...")
        
        # Invalidar cache
        invalidate_dataframe_cache()
        
        # Obter listas atualizadas
        categorias = get_unique_categories(DB_PATH, 'processos.xlsx')
        tribunais = get_unique_tribunals(DB_PATH)
        
        print(f"Categorias: {categorias}")
        print(f"Tribunais: {tribunais}")
        
        return jsonify({
            "success": True,
            "categorias": categorias,
            "tribunais": tribunais,
            "message": "Listas de filtros atualizadas com sucesso"
        })
    except Exception as e:
        print(f"Erro ao forçar atualização: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/test-simple-update", methods=["POST"])
def test_simple_update():
    """
    Endpoint de teste simples para verificar se conseguimos executar o database.py.
    ---
    """
    try:
        import subprocess
        import sys
        import time
        
        print(f"Teste simples iniciado em: {os.getcwd()}")
        
        # Verificar arquivo
        if not os.path.exists('processos.xlsx'):
            return jsonify({"error": "Arquivo processos.xlsx não encontrado"}), 400
        
        # Ler Excel para verificar
        try:
            df = pd.read_excel('processos.xlsx')
            if df.empty:
                return jsonify({"error": "Arquivo Excel está vazio"}), 400
            if 'numeroProcesso' not in df.columns:
                return jsonify({"error": "Arquivo não tem coluna numeroProcesso"}), 400
        except Exception as e:
            return jsonify({"error": f"Erro ao ler Excel: {str(e)}"}), 400
        
        # Executar database.py
        print("Executando database.py...")
        start_time = time.time()
        
        result = subprocess.run([
            sys.executable, 'database.py'
        ], capture_output=True, text=True, cwd=os.getcwd(), timeout=120)
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"database.py executado em {duration:.2f} segundos")
        print(f"Return code: {result.returncode}")
        
        # Verificar se o banco foi atualizado
        try:
            with get_conn() as conn:
                count_processos = conn.execute("SELECT COUNT(*) FROM processos").fetchone()[0]
                count_movimentos = conn.execute("SELECT COUNT(*) FROM movimentos").fetchone()[0]
                count_lista = conn.execute("SELECT COUNT(*) FROM processos_lista").fetchone()[0]
        except Exception as e:
            count_processos = count_movimentos = count_lista = f"Erro: {str(e)}"
        
        return jsonify({
            "success": result.returncode == 0,
            "return_code": result.returncode,
            "duration_seconds": duration,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "database_counts": {
                "processos": count_processos,
                "movimentos": count_movimentos,
                "processos_lista": count_lista
            },
            "excel_rows": len(df)
        })
        
    except subprocess.TimeoutExpired:
        return jsonify({
            "error": "Timeout: Execução demorou mais de 2 minutos",
            "return_code": -1
        }), 500
    except Exception as e:
        return jsonify({
            "error": f"Erro no teste simples: {str(e)}",
            "return_code": -1
        }), 500


if __name__ == "__main__":
    print("DB_PATH:", DB_PATH)
    print("ROTAS:", app.url_map)
    app.run(debug=True)
