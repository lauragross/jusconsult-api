#!/usr/bin/env python3
"""
Script para verificar o conteúdo do banco de dados
"""

import sqlite3
import os

def check_database():
    db_path = "datajud_processos.db"
    
    if not os.path.exists(db_path):
        print("❌ Banco de dados não encontrado!")
        return
    
    print("🔍 VERIFICANDO BANCO DE DADOS")
    print("=" * 40)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Verificar processos
        cursor.execute("SELECT COUNT(*) FROM processos")
        count_processos = cursor.fetchone()[0]
        print(f"📊 Total de processos: {count_processos}")
        
        # Verificar movimentos
        cursor.execute("SELECT COUNT(*) FROM movimentos")
        count_movimentos = cursor.fetchone()[0]
        print(f"📊 Total de movimentos: {count_movimentos}")
        
        # Verificar processos_lista
        cursor.execute("SELECT COUNT(*) FROM processos_lista")
        count_lista = cursor.fetchone()[0]
        print(f"📊 Total na lista mestra: {count_lista}")
        
        if count_processos > 0:
            print(f"\n📋 PROCESSOS ENCONTRADOS:")
            cursor.execute("SELECT numeroProcesso, tribunal, classe_nome FROM processos")
            for row in cursor.fetchall():
                print(f"   {row[0]} - {row[1]} - {row[2]}")
        
        if count_movimentos > 0:
            print(f"\n📋 ÚLTIMOS MOVIMENTOS:")
            cursor.execute("SELECT numeroProcesso, mov_nome, mov_dataHora FROM movimentos ORDER BY mov_dataHora DESC LIMIT 5")
            for row in cursor.fetchall():
                print(f"   {row[0]} - {row[1]} - {row[2]}")
                
    except Exception as e:
        print(f"❌ Erro ao verificar banco: {str(e)}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_database()
