"""
Script para criar dataframe auxiliar com informações de processos e movimentos.

Este script cria dois dataframes principais:
1. DataFrame principal: numeroProcesso, tribunal, categoria, sistema_nome, dataHoraUltimaAtualizacao
2. DataFrame de movimentos: numeroProcesso e mov_nome do último movimento

E realiza um left join para obter o nome do último movimento de cada processo.

Os dataframes são criados apenas em memória para uso nas telas do UI.
"""

import pandas as pd
import sqlite3
from sqlalchemy import create_engine
import os

def create_auxiliary_dataframes(db_path='datajud_processos.db', excel_path='processos.xlsx'):
    """
    Cria os dataframes auxiliares conforme solicitado.
    
    Args:
        db_path (str): Caminho para o banco SQLite
        excel_path (str): Caminho para o arquivo Excel com categorias
    
    Returns:
        tuple: (df_principal, df_movimentos, df_final)
    """
    
    # Verificar se os arquivos existem
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Banco de dados não encontrado: {db_path}")
    
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Arquivo Excel não encontrado: {excel_path}")
    
    # Conectar ao banco
    engine = create_engine(f'sqlite:///{db_path}')
    
    print("=== CRIANDO DATAFRAME PRINCIPAL ===")
    
    # 1. Carregar dados do Excel para obter categoria
    df_excel = pd.read_excel(excel_path)
    print(f"Excel carregado: {len(df_excel)} linhas")
    
    # 2. Carregar dados do banco (processos únicos)
    query_processos = """
    SELECT 
        numeroProcesso,
        tribunal,
        sistema_nome,
        MAX(dataHoraUltimaAtualizacao) as dataHoraUltimaAtualizacao
    FROM processos
    GROUP BY numeroProcesso, tribunal, sistema_nome
    """
    
    df_processos = pd.read_sql(query_processos, engine)
    print(f"Processos únicos do banco: {len(df_processos)} linhas")
    
    # 3. Merge com Excel para obter categoria
    df_principal = df_processos.merge(
        df_excel[['numeroProcesso', 'categoria']], 
        on='numeroProcesso', 
        how='left'
    )
    
    # Limpar categoria (remover espaços extras)
    df_principal['categoria'] = df_principal['categoria'].str.strip()
    
    print(f"Dataframe principal criado: {len(df_principal)} linhas")
    print(f"Colunas: {df_principal.columns.tolist()}")
    
    print("\n=== CRIANDO DATAFRAME DE MOVIMENTOS ===")
    
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
    
    df_movimentos = pd.read_sql(query_movimentos, engine)
    print(f"Dataframe de movimentos criado: {len(df_movimentos)} linhas")
    print(f"Colunas: {df_movimentos.columns.tolist()}")
    
    print("\n=== CRIANDO DATAFRAME FINAL ===")
    
    # 5. Left join para obter nome do último movimento
    df_final = df_principal.merge(
        df_movimentos, 
        on='numeroProcesso', 
        how='left'
    )
    
    print(f"Dataframe final criado: {len(df_final)} linhas")
    
    # Estatísticas
    print(f"\n=== ESTATÍSTICAS ===")
    print(f"- Processos únicos: {df_final['numeroProcesso'].nunique()}")
    print(f"- Processos com movimento: {df_final['mov_nome'].notna().sum()}")
    print(f"- Processos sem movimento: {df_final['mov_nome'].isna().sum()}")
    
    if not df_final.empty:
        print(f"\nCategorias:")
        for cat, count in df_final["categoria"].value_counts().items():
            print(f"  - {cat}: {count}")
        
        print(f"\nTribunais:")
        for trib, count in df_final["tribunal"].value_counts().items():
            print(f"  - {trib}: {count}")
    
    return df_principal, df_movimentos, df_final

def show_dataframe_info(df_principal, df_movimentos, df_final):
    """
    Exibe informações sobre os dataframes criados.
    
    Args:
        df_principal: DataFrame principal
        df_movimentos: DataFrame de movimentos  
        df_final: DataFrame final
    """
    
    print(f"\n✅ Dataframes criados com sucesso:")
    print(f"  - DataFrame principal: {len(df_principal)} linhas")
    print(f"  - DataFrame movimentos: {len(df_movimentos)} linhas")
    print(f"  - DataFrame final: {len(df_final)} linhas")

def main():
    """
    Função principal para executar o processo completo.
    """
    try:
        # Criar os dataframes
        df_principal, df_movimentos, df_final = create_auxiliary_dataframes()
        
        # Mostrar resultado
        print(f"\n=== DATAFRAME FINAL ===")
        print(df_final.to_string())
        
        # Mostrar informações dos dataframes
        show_dataframe_info(df_principal, df_movimentos, df_final)
        
        return df_principal, df_movimentos, df_final
        
    except Exception as e:
        print(f"Erro: {str(e)}")
        raise

if __name__ == "__main__":
    main()
