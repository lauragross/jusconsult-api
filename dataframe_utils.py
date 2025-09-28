"""
Utilitários para criação de dataframes auxiliares para as telas do UI.

Este módulo fornece funções para criar dataframes com informações de processos
e movimentos que serão utilizados nas interfaces do usuário.

Inclui sistema de cache para melhorar performance e invalidação automática
quando o banco de dados for atualizado.
"""

import pandas as pd
from sqlalchemy import create_engine
import os
import time
import threading
import re

# Cache global para os dataframes
_dataframe_cache = {
    'data': None,
    'last_update': 0,
    'lock': threading.Lock()
}

# Flag para forçar atualização do cache
_cache_invalidated = False

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

def get_auxiliary_dataframes(db_path='datajud_processos.db', excel_path='processos.xlsx', force_refresh=False):
    """
    Cria os dataframes auxiliares para uso nas telas do UI.
    Usa cache para melhorar performance e só recria quando necessário.
    
    Args:
        db_path (str): Caminho para o banco SQLite
        excel_path (str): Caminho para o arquivo Excel com categorias
        force_refresh (bool): Força a atualização do cache
    
    Returns:
        dict: Dicionário contendo os dataframes:
            - 'principal': DataFrame com numeroProcesso, tribunal, categoria, sistema_nome, dataHoraUltimaAtualizacao
            - 'movements': DataFrame com numeroProcesso e mov_nome do último movimento
            - 'final': DataFrame final com left join entre principal e movements
    """
    global _dataframe_cache, _cache_invalidated
    
    with _dataframe_cache['lock']:
        current_time = time.time()
        
        # Verificar se precisa atualizar o cache
        needs_update = (
            force_refresh or
            _cache_invalidated or
            _dataframe_cache['data'] is None or
            not _is_cache_valid(db_path, excel_path)
        )
        
        if needs_update:
            print("🔄 Atualizando cache dos dataframes auxiliares...")
            _dataframe_cache['data'] = _create_dataframes(db_path, excel_path)
            _dataframe_cache['last_update'] = current_time
            _cache_invalidated = False
            print("✅ Cache dos dataframes atualizado!")
        else:
            print("📋 Usando cache dos dataframes (última atualização: {:.1f}s atrás)".format(
                current_time - _dataframe_cache['last_update']
            ))
        
        return _dataframe_cache['data']

def _is_cache_valid(db_path, excel_path):
    """
    Verifica se o cache ainda é válido comparando timestamps dos arquivos.
    """
    try:
        if not os.path.exists(db_path) or not os.path.exists(excel_path):
            return False
        
        db_mtime = os.path.getmtime(db_path)
        excel_mtime = os.path.getmtime(excel_path)
        
        # Cache é válido se os arquivos não foram modificados desde a última atualização
        return (db_mtime < _dataframe_cache['last_update'] and 
                excel_mtime < _dataframe_cache['last_update'])
    except OSError:
        return False

def _create_dataframes(db_path, excel_path):
    """
    Função interna para criar os dataframes (sem cache).
    """
    # Verificar se os arquivos existem
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Banco de dados não encontrado: {db_path}")
    
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Arquivo Excel não encontrado: {excel_path}")
    
    # Conectar ao banco
    engine = create_engine(f'sqlite:///{db_path}')
    
    # 1. Carregar dados do Excel para obter categoria
    df_excel = pd.read_excel(excel_path)
    
    # Normalizar números de processo no Excel para fazer o match com o banco
    df_excel['numeroProcesso_normalizado'] = df_excel['numeroProcesso'].map(normaliza_nup)
    
    # CORREÇÃO: Remover duplicatas do Excel baseado no numeroProcesso normalizado
    # Manter apenas a primeira ocorrência de cada processo único
    df_excel = df_excel.drop_duplicates(subset=['numeroProcesso_normalizado'], keep='first')
    
    # 2. Carregar dados do banco (processos únicos)
    # CORREÇÃO: Usar apenas numeroProcesso no GROUP BY para evitar duplicatas
    # Se um processo tem múltiplos registros com diferentes tribunais/sistemas,
    # manteremos apenas um registro por numeroProcesso (o mais recente)
    query_processos = """
    WITH processos_unicos AS (
        SELECT 
            numeroProcesso,
            tribunal,
            sistema_nome,
            dataHoraUltimaAtualizacao,
            ROW_NUMBER() OVER (
                PARTITION BY numeroProcesso 
                ORDER BY dataHoraUltimaAtualizacao DESC
            ) as rn
        FROM processos
    )
    SELECT 
        numeroProcesso,
        tribunal,
        sistema_nome,
        dataHoraUltimaAtualizacao
    FROM processos_unicos
    WHERE rn = 1
    """
    
    df_processos = pd.read_sql(query_processos, engine)
    
    # 3. Merge com Excel para obter categoria (usando número normalizado)
    df_principal = df_processos.merge(
        df_excel[['numeroProcesso_normalizado', 'categoria']], 
        left_on='numeroProcesso', 
        right_on='numeroProcesso_normalizado',
        how='left'
    )
    
    # Remover coluna auxiliar
    df_principal = df_principal.drop('numeroProcesso_normalizado', axis=1)
    
    # Limpar categoria (remover espaços extras)
    df_principal['categoria'] = df_principal['categoria'].str.strip()
    
    # 4. Query para obter o último movimento de cada processo
    query_movimentos = """
    WITH ultimo_movimento AS (
        SELECT 
            numeroProcesso,
            mov_nome,
            mov_dataHora,
            ROW_NUMBER() OVER (
                PARTITION BY numeroProcesso 
                ORDER BY mov_dataHora DESC
            ) as rn
        FROM movimentos
        WHERE mov_dataHora IS NOT NULL
    )
    SELECT 
        numeroProcesso,
        mov_nome
    FROM ultimo_movimento
    WHERE rn = 1
    """
    
    df_movements = pd.read_sql(query_movimentos, engine)
    
    # 5. Left join para obter nome do último movimento
    df_final = df_principal.merge(
        df_movements, 
        on='numeroProcesso', 
        how='left'
    )
    
    return {
        'principal': df_principal,
        'movements': df_movements,
        'final': df_final
    }

def invalidate_dataframe_cache():
    """
    Invalida o cache dos dataframes auxiliares.
    Deve ser chamada sempre que o banco de dados for atualizado.
    """
    global _cache_invalidated
    
    with _dataframe_cache['lock']:
        _cache_invalidated = True
        print("🗑️ Cache dos dataframes auxiliares invalidado!")

def get_unique_categories(db_path='datajud_processos.db', excel_path='processos.xlsx'):
    """
    Retorna lista única de categorias sem duplicatas.
    IMPORTANTE: Retorna apenas categorias que existem no banco de dados atual.
    SEM CACHE - sempre busca dados atuais.
    
    Args:
        db_path (str): Caminho para o banco SQLite
        excel_path (str): Caminho para o arquivo Excel com categorias
    
    Returns:
        list: Lista ordenada de categorias únicas que existem no banco
    """
    try:
        from sqlalchemy import create_engine
        
        print(f"🔍 Buscando categorias em {db_path} e {excel_path}")
        
        # Conectar ao banco
        engine = create_engine(f'sqlite:///{db_path}')
        
        # 1. Pegar todos os números de processo que existem no banco
        df_banco = pd.read_sql("SELECT DISTINCT numeroProcesso FROM processos", engine)
        print(f"📊 Processos no banco: {len(df_banco)}")
        
        # Converter para set para busca rápida
        numeros_banco = set()
        for _, row in df_banco.iterrows():
            numero_limpo = normaliza_nup(row['numeroProcesso'])
            numeros_banco.add(numero_limpo)
        
        # 2. Ler Excel e normalizar números
        df_excel = pd.read_excel(excel_path)
        print(f"📊 Processos no Excel: {len(df_excel)}")
        
        # 3. Pegar apenas categorias de processos que existem no banco
        categorias = set()
        for _, row in df_excel.iterrows():
            numero_limpo = normaliza_nup(row['numeroProcesso'])
            if numero_limpo in numeros_banco:
                categoria = row.get('categoria')
                if categoria and str(categoria).strip() != '':
                    # Limpar e normalizar categoria
                    categoria_limpa = str(categoria).strip()
                    # Remover caracteres problemáticos se necessário
                    categoria_limpa = categoria_limpa.replace('\xa0', ' ')  # Remove non-breaking spaces
                    categorias.add(categoria_limpa)
                    print(f"🔍 Adicionando categoria: '{categoria_limpa}'")
        
        # 4. Converter para lista ordenada
        categorias = sorted(list(categorias))
        
        print(f"✅ Categorias encontradas: {categorias}")
        return categorias
    except Exception as e:
        print(f"❌ Erro ao obter categorias: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

def get_unique_tribunals(db_path='datajud_processos.db'):
    """
    Retorna lista única de tribunais sem duplicatas.
    IMPORTANTE: Retorna apenas tribunais que existem no banco de dados atual.
    
    Args:
        db_path (str): Caminho para o banco SQLite
    
    Returns:
        list: Lista ordenada de tribunais únicos que existem no banco
    """
    try:
        from sqlalchemy import create_engine
        
        # Conectar ao banco
        engine = create_engine(f'sqlite:///{db_path}')
        
        # Query para obter tribunais únicos
        query = """
            SELECT DISTINCT tribunal 
            FROM processos 
            WHERE tribunal IS NOT NULL 
            ORDER BY tribunal
        """
        
        df_tribunais = pd.read_sql(query, engine)
        tribunais = df_tribunais['tribunal'].tolist()
        
        # Remover duplicatas e ordenar (caso ainda existam)
        tribunais = sorted(list(set(tribunais)))
        
        return tribunais
    except Exception as e:
        print(f"❌ Erro ao obter tribunais: {str(e)}")
        return []

def update_filter_lists(db_path='datajud_processos.db', excel_path='processos.xlsx'):
    """
    Atualiza as listas de categorias e tribunais após atualização do banco.
    Garante que não há duplicatas nas listas.
    SEM CACHE - sempre busca dados atuais.
    
    Args:
        db_path (str): Caminho para o banco SQLite
        excel_path (str): Caminho para o arquivo Excel com categorias
    
    Returns:
        dict: Dicionário com as listas atualizadas
    """
    try:
        print("🔄 Atualizando listas de filtros (categorias e tribunais)...")
        
        # Obter listas únicas (sem cache)
        categorias = get_unique_categories(db_path, excel_path)
        tribunais = get_unique_tribunals(db_path)
        
        print(f"✅ Categorias atualizadas: {len(categorias)} itens")
        print(f"✅ Tribunais atualizados: {len(tribunais)} itens")
        
        return {
            'categorias': categorias,
            'tribunais': tribunais
        }
    except Exception as e:
        print(f"❌ Erro ao atualizar listas de filtros: {str(e)}")
        return {
            'categorias': [],
            'tribunais': []
        }

def get_processes_summary():
    """
    Retorna um resumo dos processos para exibição no UI.
    
    Returns:
        dict: Dicionário com estatísticas dos processos
    """
    try:
        dataframes = get_auxiliary_dataframes()
        df_final = dataframes['final']
        
        if df_final.empty:
            return {
                'total_processes': 0,
                'unique_processes': 0,
                'with_movements': 0,
                'without_movements': 0,
                'categories': {},
                'tribunals': {}
            }
        
        return {
            'total_processes': len(df_final),
            'unique_processes': df_final['numeroProcesso'].nunique(),
            'with_movements': df_final['mov_nome'].notna().sum(),
            'without_movements': df_final['mov_nome'].isna().sum(),
            'categories': df_final["categoria"].value_counts().to_dict(),
            'tribunals': df_final["tribunal"].value_counts().to_dict()
        }
    except Exception as e:
        return {'error': str(e)}

def get_processes_by_category(category=None):
    """
    Retorna processos filtrados por categoria.
    
    Args:
        category (str): Categoria para filtrar (opcional)
    
    Returns:
        pandas.DataFrame: DataFrame filtrado
    """
    try:
        dataframes = get_auxiliary_dataframes()
        df_final = dataframes['final']
        
        if category:
            return df_final[df_final['categoria'] == category]
        else:
            return df_final
    except Exception as e:
        return pd.DataFrame()

def get_processes_by_tribunal(tribunal=None):
    """
    Retorna processos filtrados por tribunal.
    
    Args:
        tribunal (str): Tribunal para filtrar (opcional)
    
    Returns:
        pandas.DataFrame: DataFrame filtrado
    """
    try:
        dataframes = get_auxiliary_dataframes()
        df_final = dataframes['final']
        
        if tribunal:
            return df_final[df_final['tribunal'] == tribunal]
        else:
            return df_final
    except Exception as e:
        return pd.DataFrame()

if __name__ == "__main__":
    # Teste das funções
    print("=== TESTANDO FUNÇÕES ===")
    
    try:
        # Testar função principal
        dataframes = get_auxiliary_dataframes()
        print(f"✅ Dataframes criados:")
        print(f"  - Principal: {len(dataframes['principal'])} linhas")
        print(f"  - Movements: {len(dataframes['movements'])} linhas")
        print(f"  - Final: {len(dataframes['final'])} linhas")
        
        # Testar resumo
        summary = get_processes_summary()
        print(f"\n✅ Resumo:")
        print(f"  - Total: {summary['total_processes']}")
        print(f"  - Únicos: {summary['unique_processes']}")
        print(f"  - Com movimentos: {summary['with_movements']}")
        
        # Testar filtros
        fumicultores = get_processes_by_category('Fumicultores')
        print(f"\n✅ Fumicultores: {len(fumicultores)} processos")
        
        # Testar novas funções de listas únicas
        print(f"\n=== TESTANDO LISTAS ÚNICAS (APENAS DADOS EXISTENTES) ===")
        categorias = get_unique_categories()
        tribunais = get_unique_tribunals()
        
        print(f"✅ Categorias únicas (apenas do banco): {len(categorias)} itens")
        print(f"   Todas as categorias: {categorias}")
        
        print(f"✅ Tribunais únicos (apenas do banco): {len(tribunais)} itens")
        print(f"   Todos os tribunais: {tribunais}")
        
        # Testar função de atualização de listas
        print(f"\n=== TESTANDO ATUALIZAÇÃO DE LISTAS ===")
        filter_lists = update_filter_lists()
        print(f"✅ Listas atualizadas:")
        print(f"   - Categorias: {len(filter_lists['categorias'])} itens")
        print(f"   - Tribunais: {len(filter_lists['tribunais'])} itens")
        
        # Verificar se as listas estão corretas
        print(f"\n=== VERIFICAÇÃO DE INTEGRIDADE ===")
        if len(categorias) > 0:
            print(f"✅ Categorias encontradas: {categorias}")
        else:
            print(f"⚠️ Nenhuma categoria encontrada - verifique se há processos no banco")
            
        if len(tribunais) > 0:
            print(f"✅ Tribunais encontrados: {tribunais}")
        else:
            print(f"⚠️ Nenhum tribunal encontrado - verifique se há processos no banco")
        
    except Exception as e:
        print(f"❌ Erro: {str(e)}")
        import traceback
        traceback.print_exc()
