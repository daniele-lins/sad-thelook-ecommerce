# 🛒 TheLook SAD — Sistema de Apoio à Decisão de Marketing

> **Protótipo Funcional Executável para Orientação de Campanhas Promocionais, Segmentação RFM e Análise de LTV**  
> *Projeto desenvolvido para a disciplina de Sistemas de Apoio à Decisão (SAD) — Universidade Federal da Bahia (UFBA).*

---

## 📌 1. Descrição do Sistema e Escopo Decisório

### 🎯 Objetivo e Propósito
O **TheLook SAD** é um Sistema de Apoio à Decisão (SAD) projetado para otimizar o planejamento de campanhas de marketing e a alocação de orçamentos em plataformas de e-commerce. Utilizando a base de dados pública e massiva do marketplace **TheLook E-Commerce** (extraída do BigQuery/Kaggle), o sistema transforma dados operacionais brutos em diagnósticos preditivos e prescritivos.

### 👤 Usuários e Decisores
- **Gestores e Diretores de Marketing (CMOs)**: Avaliação do retorno financeiro (ROMI/ROI) e viabilidade de cenários promocionais.
- **Analistas de CRM e Growth**: Identificação de perfis comportamentais de clientes (RFM) e mitigação de churn.
- **Gerentes de Produto e E-commerce**: Acompanhamento da taxa de conversão do funil de vendas, ticket médio (AOV) e LTV por canal.

### 🏛️ Classificação da Decisão
- **Nível Gerencial**: Tático e Estratégico (planejamento de campanhas trimestrais/anuais, orçamento de mídia e retenção de clientes).
- **Grau de Estruturação**: Semiestruturado (embora os dados históricos sejam quantitativos, a definição da taxa de resposta, desconto promocional e meta de ROMI exige o julgamento e a sensibilidade do gestor).

---

## ⚙️ 2. Arquitetura, Dados e Funções Analíticas

### 🗄️ Fonte de Dados e Armazenamento
- **Dataset de Origem**: [*Looker E-Commerce BigQuery Dataset* (Kaggle)](https://www.kaggle.com/datasets/mustafakeser4/looker-ecommerce-bigquery-dataset).
- **Mecanismo de Ingestão e Cache**: Download automatizado via `kagglehub` e conversão nativa para arquivos comprimidos `.parquet` (PyArrow Snappy).
- **Motor de Banco de Dados**: **DuckDB em memória (`:memory:`)**, garantindo consultas analíticas (OLAP) em tempo de execução com altíssima performance.

### 🔬 Funções Analíticas Empregadas

O sistema atende à exigência metodológica ao empregar formalmente três funções analíticas complementares:

1. **Sumarização e Métricas Agregadas (OLAP)**:
   - **Entrada**: Tabelas de pedidos (`orders`), itens (`order_items`), eventos (`events`) e usuários (`users`).
   - **Processamento**: Consultas analíticas no DuckDB com agregações dinâmicas de faturamento, lucro bruto, ticket médio (AOV), taxa de conversão do funil de vendas e LTV.
   - **Resultado Decisório**: Diagnóstico situacional e monitoramento dos KPIs do e-commerce.

2. **Agrupamento / Clusterização Preditiva (K-Means sobre RFM)**:
   - **Entrada**: Métricas individuais de **Recência** (dias sem comprar), **Frequência** (nº de pedidos concluídos) e **Valor Monetário** (total investido em US$).
   - **Processamento**: Padronização dos dados (`StandardScaler`) e aplicação do algoritmo de Machine Learning **K-Means ($k=4$)**.
   - **Resultado Decisório**: Segmentação comportamental da base em 4 perfis comerciais bem definidos:
     - 💰 **Clientes de Alto-Valor**: Alta frequência e alto ticket médio.
     - 💤 **Clientes Inativos**: Alto tempo de recência e baixo engajamento recente.
     - 💜 **Clientes Leais**: Compras recorrentes e estáveis.
     - 🌱 **Clientes Promissores**: Clientes novos com alto potencial de rentabilização.

3. **Classificação Determinística Baseada em Regras (Rule-Based Classifier)**:
   - **Entrada**: Alavancas promocionais configuradas pelo usuário (Taxa de Resposta Base %, Desconto Promocional %, Custo Fixo por Segmento US$ e Meta de ROMI) cruzadas com os resultados projetados de receita e custos.
   - **Processamento**: Motor de decisão lógico baseado em heurísticas e condicionais aninhadas (`if-else`), que aplicam funções de decaimento por recência (`exp(-0.5 * recencia_seg / recencia_global)`) e avaliam o atingimento do ROMI limite em relação à meta fixada.
   - **Resultado Decisório**: Rotulagem categórica automatizada da viabilidade de cada segmento em **🟢 Bom**, **🟡 Médio** ou **🔴 Ruim**, acompanhada de pareceres prescritivos com recomendações de ação para o gestor.

---

## 💻 3. Requisitos de Infraestrutura e Espaço em Disco

Para clonar e executar o protótipo localmente, certifique-se de atender aos seguintes pré-requisitos:

| Requisito | Especificação Recomendada |
| :--- | :--- |
| **Linguagem** | Python 3.11.x (ou 3.10+) |
| **Espaço Livre em Disco** | **~1,5 GB** |
| **Memória RAM** | 4 GB ou superior |
| **Sistemas Operacionais** | Windows 10/11, macOS ou Linux |

> ℹ️ **Nota sobre o Espaço em Disco (1,3 GB - 1,5 GB):**  
> Na primeira execução, o sistema realiza o download automático do dataset bruto via KaggleHub e constrói o banco de dados otimizado em `.parquet` na pasta `data_parquet/`. Somados às dependências do ambiente virtual (`.venv`) e ao histórico de controle de versão (`.git`), o projeto aloca aproximadamente 1,3 GB a 1,5 GB de armazenamento local.

---

## 🚀 4. Instruções de Instalação e Execução

### Passo 1: Clonar o Repositório
```bash
git clone https://github.com/daniele-lins/sad-thelook-ecommerce.git
cd sad-thelook-ecommerce
```

### Passo 2: Criar e Ativar o Ambiente Virtual (`.venv`)

- **Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

- **Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Passo 3: Instalar as Dependências
```bash
pip install -r requirements.txt
```

### Passo 4: Executar a Aplicação Streamlit
```bash
streamlit run app.py
```

A aplicação será aberta automaticamente no seu navegador no endereço `http://localhost:8501`.

---

## 🔐 5. Credenciais de Teste

Como o protótipo opera integralmente em ambiente local (sem persistência em nuvem nesta etapa), há uma credencial padrão pré-configurada para acesso e avaliação das funcionalidades do sistema:

| Usuário | Senha 
| :--- | :--- 
| `admin@ecommerce.com` | `123456`