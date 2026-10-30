import streamlit as st
from views import login, dashboard, simulador, relatorios
from base_de_dados import carregar_banco

st.set_page_config(page_title="TheLook E-commerce - Sistema de Apoio à Decisão de Marketing", layout="wide")

# Inicializa o estado de login
if 'logado' not in st.session_state:
    st.session_state['logado'] = False

# Se não estiver logado, exibe apenas a tela de login
if not st.session_state['logado']:
    login.renderizar()
else:
    # Carrega a conexão com o DuckDB
    con = carregar_banco()
    
    # Barra lateral de navegação e logout
    st.sidebar.title("TheLook SAD")
    st.sidebar.markdown("---")
    st.sidebar.subheader("**📌 Menu de Navegação**")
    st.sidebar.write(f"👤 Logado como: **{st.session_state.get('usuario_atual', 'Usuário')}**")
    
    pagina = st.sidebar.radio(
        "Ir para:", 
        ["Dashboard Principal", "Módulo de Simulação", "Central de Relatórios"]
    )
    
    if st.sidebar.button("🚪 Sair / Logout"):
        st.session_state['logado'] = False
        st.rerun()
    
    # Renderiza a página selecionada
    if pagina == "Dashboard Principal":
        dashboard.renderizar(con.cursor())
    elif pagina == "Módulo de Simulação":
        simulador.renderizar(con.cursor())
    elif pagina == "Central de Relatórios":
        relatorios.renderizar(con.cursor())