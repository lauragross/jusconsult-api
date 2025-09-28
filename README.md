# JusConsult API

## Descrição do Projeto

A **JusConsult API** é uma aplicação Flask que fornece uma interface REST para consulta e gerenciamento de dados de processos judiciais obtidos através da API pública do DataJud (Conselho Nacional de Justiça). A aplicação permite:

- Consulta de processos judiciais por número
- Visualização de movimentações processuais
- Filtros por tribunal e categoria
- Upload e gerenciamento de listas de processos via Excel
- Atualização automática do banco de dados
- Interface web para visualização dos dados

## Arquitetura da Aplicação

```mermaid
graph TB
    subgraph "Frontend"
        UI[Interface Web]
    end
    
    subgraph "Backend"
        API[Flask API]
    end
    
    subgraph "Dados"
        EXCEL[Excel<br/>Lista de Processos]
        SQLITE[(SQLite Database)]
    end
    
    subgraph "Externo"
        DATAJUD[DataJud API<br/>CNJ]
    end
    
    UI --> API
    API --> SQLITE
    API --> EXCEL
    API --> DATAJUD
```

## Instalação e Configuração

### Pré-requisitos

- Python 3.8 ou superior
- pip (gerenciador de pacotes Python)
- Git (para clonar o repositório)

### 1. Clone o Repositório

```bash
git clone <url-do-repositorio>
cd jusconsult-api
```

### 2. Criação do Ambiente Virtual

```bash
# Criar ambiente virtual
python -m venv venv

# Ativar ambiente virtual
# No Windows:
venv\Scripts\activate
# No Linux/Mac:
source venv/bin/activate
```

### 3. Instalação das Dependências

```bash
pip install -r requirements.txt
```

### 4. Configuração do Ambiente

Crie um arquivo `.env` na raiz do projeto (opcional):

```env
# Configurações do banco de dados
JUSCONSULT_DB_PATH=jusconsult_processos.db

# Configurações do Flask
FLASK_ENV=development
FLASK_RUN_HOST=0.0.0.0
FLASK_RUN_PORT=5000

# API Key do DataJud (opcional - há uma chave padrão no código)
DATAJUD_APIKEY=sua_chave_aqui
```

### 5. Inicialização do Banco de Dados

O projeto já inclui um arquivo `processos.xlsx` de exemplo. Para inicializar o banco de dados:

```bash
# Executar script de atualização do banco
python database.py
```

Este comando irá:
- Criar o banco SQLite se não existir
- Consultar a API do DataJud para cada processo do arquivo Excel
- Salvar os dados no banco local

## Executando a Aplicação

```bash
# Executar a aplicação
python app.py
```

A aplicação estará disponível em:
- **API**: http://localhost:5000
- **Documentação Swagger**: http://localhost:5000/apidocs

## Endpoints da API

### Processos

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/processos` | Lista processos com filtros |
| GET | `/processos-lista` | Lista mestra de processos |
| GET | `/processo/<numero>` | Dados completos de um processo |

### Movimentações

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/movimentos/<numero>` | Movimentações de um processo |

### Filtros e Categorias

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/tribunais` | Lista de tribunais disponíveis |
| GET | `/categorias` | Lista de categorias disponíveis |

### Atualizações

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/atualizacoes` | Processos agrupados por período |
| GET | `/atualizacoes-dataframe` | Atualizações com dados do Excel |

### Upload e Gerenciamento

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/upload-processos` | Upload de arquivo Excel |
| GET | `/template-excel` | Download do template Excel |
| POST | `/confirm-replace` | Confirma substituição do Excel |
| POST | `/update-database` | Atualiza banco de dados |
| POST | `/update-database-stream` | Atualização com streaming |

### Utilitários

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/health` | Verificação de saúde |
| POST | `/clear-database` | Limpa banco de dados |
| POST | `/update-filter-lists` | Atualiza listas de filtros |

## Comandos Úteis

### Verificação do Banco

```bash
# Verificar conteúdo do banco
python check_db.py
```

### Teste das Funções

```bash
# Testar funções de dataframe
python dataframe_utils.py
```

## Estrutura do Projeto

```
jusconsult-api/
├── app.py                 # Aplicação Flask principal
├── database.py            # Script de atualização do banco
├── utils.py               # Utilitários de conexão
├── dataframe_utils.py     # Utilitários de dataframe e cache
├── check_db.py            # Script de verificação do banco
├── requirements.txt       # Dependências Python
├── processos.xlsx         # Lista de processos (exemplo)
├── jusconsult_processos.db   # Banco SQLite (gerado)
└── README.md              # Este arquivo
```

## Estrutura do Banco de Dados

### Tabela `processos`
Armazena informações principais dos processos:
- `numeroProcesso`: Número único do processo
- `tribunal`: Código do tribunal
- `classe_nome`: Nome da classe processual
- `sistema_nome`: Nome do sistema
- `dataHoraUltimaAtualizacao`: Data da última atualização

### Tabela `movimentos`
Armazena movimentações processuais:
- `numeroProcesso`: Referência ao processo
- `mov_nome`: Nome do movimento
- `mov_dataHora`: Data e hora do movimento
- `mov_orgao_nome`: Órgão responsável

### Tabela `processos_lista`
Índice mestre de processos:
- `numeroProcesso`: Chave primária
- `tribunal_inicial`: Tribunal onde foi encontrado
- `primeiraInclusao`: Data da primeira inclusão
- `ultimoUpdate`: Data da última atualização

## Configurações Avançadas

### Variáveis de Ambiente

| Variável | Descrição | Padrão |
|----------|-----------|---------|
| `JUSCONSULT_DB_PATH` | Caminho do banco SQLite | `jusconsult_processos.db` |
| `FLASK_ENV` | Ambiente Flask | `production` |
| `FLASK_RUN_HOST` | Host de execução | `0.0.0.0` |
| `FLASK_RUN_PORT` | Porta de execução | `5000` |
| `DATAJUD_APIKEY` | Chave da API DataJud | Chave padrão incluída |

### Otimizações

1. **Cache de DataFrames**: Sistema de cache automático para melhorar performance
2. **Busca Otimizada**: Se o Excel contém coluna `tribunal`, busca apenas no tribunal específico
3. **Paginação**: Endpoints suportam paginação com `limit` e `offset`
4. **Streaming**: Atualização do banco com feedback em tempo real

---

**JusConsult API** - Interface REST para consulta de processos judiciais via API do CNJ