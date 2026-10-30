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
    
    if st.sidebar.button("🚪 Sair / Logout", type="tertiary"):
            st.session_state['logado'] = False
            st.rerun()
    
    # Inicialização da página padrão no session_state (caso ainda não exista)
    if "pagina" not in st.session_state:
        st.session_state.pagina = "dashboard"

    # Botões de Navegação na Sidebar
    if st.sidebar.button(
        "📊 Dashboard Executivo",
        use_container_width=True,
        type="primary" if st.session_state.pagina == "dashboard" else "secondary",
    ):
        st.session_state.pagina = "dashboard"
        st.rerun()

    if st.sidebar.button(
        "🔮 Simulador Preditivo",
        use_container_width=True,
        type="primary" if st.session_state.pagina == "simulador" else "secondary",
    ):
        st.session_state.pagina = "simulador"
        st.rerun()

    if st.sidebar.button(
        "📄 Relatório de SAD",
        use_container_width=True,
        type="primary" if st.session_state.pagina == "relatorio" else "secondary",
    ):
        st.session_state.pagina = "relatorio"
        st.rerun()

    # 3. Renderização Condicional da Página Selecionada
    if st.session_state.pagina == "dashboard":
        dashboard.renderizar(con.cursor())
    elif st.session_state.pagina == "simulador":
        st.title("🔮 Simulador Preditivo & Clusterização")
        st.info("Módulo de Simulação Preditiva / K-Means em desenvolvimento.")
    elif st.session_state.pagina == "relatorio":
        st.title("📄 Relatório do Sistema de Apoio à Decisão")
        st.info("Módulo de Relatórios e Documentação do SAD.")