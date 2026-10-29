import os
import duckdb
import pandas as pd
import streamlit as st

PASTA_SAIDA = "data_parquet"
TABELAS = [
    'users', 
    'orders', 
    'order_items', 
    'products', 
    'inventory_items', 
    'events', 
    'distribution_centers'
]

def inicializar_base_de_dados():
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    
    # Verifica se já existem arquivos parquet na pasta
    arquivos_existentes = os.listdir(PASTA_SAIDA)
    precisa_converter = any(f"{t}.parquet" not in arquivos_existentes for t in TABELAS)
    
    if precisa_converter:
        import kagglehub
        
        os.environ["KAGGLEHUB_CACHE"] = r"D:\kagglehub_cache"
        path = kagglehub.dataset_download("mustafakeser4/looker-ecommerce-bigquery-dataset")
        
        for tabela in TABELAS:
            caminho_csv = os.path.join(path, f"{tabela}.csv")
            caminho_parquet = os.path.join(PASTA_SAIDA, f"{tabela}.parquet")
            
            if os.path.exists(caminho_csv):
                df = pd.read_csv(caminho_csv)
                df.to_parquet(caminho_parquet, engine='pyarrow', compression='snappy', index=False)             

# Executa a checagem/conversão inicial
inicializar_base_de_dados()

@st.cache_resource
def carregar_banco():
    con = duckdb.connect(database=':memory:')

    con.execute("CREATE OR REPLACE TABLE users AS SELECT * FROM 'data_parquet/users.parquet'")
    con.execute("CREATE OR REPLACE TABLE orders AS SELECT * FROM 'data_parquet/orders.parquet'")
    con.execute("CREATE OR REPLACE TABLE order_items AS SELECT * FROM 'data_parquet/order_items.parquet'")
    con.execute("CREATE OR REPLACE TABLE products AS SELECT * FROM 'data_parquet/products.parquet'")
    con.execute("CREATE OR REPLACE TABLE events AS SELECT * FROM 'data_parquet/events.parquet'")
    con.execute("CREATE OR REPLACE TABLE inventory_items AS SELECT * FROM 'data_parquet/inventory_items.parquet'")
    con.execute("CREATE OR REPLACE TABLE distribution_centers AS SELECT * FROM 'data_parquet/distribution_centers.parquet'")
    return con

# Instância da conexão para o Streamlit
con = carregar_banco()