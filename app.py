import time
import streamlit as st
import streamlit.components.v1 as components
from telas import login, dashboard, simulador, relatorios
from base_de_dados import carregar_banco

st.set_page_config(
    page_title="TheLook E-commerce - Sistema de Apoio à Decisão de Marketing",
    layout="wide",
)

# Inicializa o estado de login
if "logado" not in st.session_state:
    st.session_state["logado"] = False

# Se não estiver logado, exibe apenas a tela de login
if not st.session_state["logado"]:
    login.renderizar()
else:
    # Carrega a conexão com o DuckDB
    con = carregar_banco()

    # Barra lateral de navegação e logout
    st.sidebar.title("TheLook SAD")
    st.sidebar.markdown("---")
    st.sidebar.subheader("**📌 Menu de Navegação**")
    st.sidebar.write(
        f"👤 Logado como: **{st.session_state.get('usuario_atual', 'Usuário')}**"
    )

    if st.sidebar.button("🚪 Sair / Logout", type="tertiary"):
        st.session_state["logado"] = False
        st.rerun()

    # Inicialização da página padrão e âncora
    if "pagina" not in st.session_state:
        st.session_state.pagina = "dashboard"
    if "ancora_destino" not in st.session_state:
        st.session_state.ancora_destino = None

    # Botões de Navegação na Sidebar apontando para o título de cada aba
    if st.sidebar.button(
        "📊 Dashboard",
        use_container_width=True,
        type="primary" if st.session_state.pagina == "dashboard" else "secondary",
    ):
        st.session_state.pagina = "dashboard"
        st.session_state.ancora_destino = "dashboard-de-performance-and-marketing"
        st.rerun()

    if st.sidebar.button(
        "🔮 Módulo de Simulação",
        use_container_width=True,
        type="primary" if st.session_state.pagina == "simulador" else "secondary",
    ):
        st.session_state.pagina = "simulador"
        st.session_state.ancora_destino = "modulo-de-simulacao-preditiva-and-clusterizacao-de-clientes"
        st.rerun()

    if st.sidebar.button(
        "📄 Relatórios",
        use_container_width=True,
        type="primary" if st.session_state.pagina == "relatorio" else "secondary",
    ):
        st.session_state.pagina = "relatorio"
        st.session_state.ancora_destino = "relatorios-analiticos"
        st.rerun()

    # 3. Dispara o observador de rolagem ANTES de montar os gráficos da nova aba
    ancora = st.session_state.get("ancora_destino")
    if ancora:
        st.session_state.ancora_destino = None
        ts = int(time.time() * 1000)
        comportamento = "instant"

        components.html(
            f"""
            <!-- nav_scroll_{ts} -->
            <script>
                (function() {{
                    const doc = window.parent.document;
                    const targetId = {repr(ancora)};
                    const scrollBehavior = {repr(comportamento)};

                    function jumpToTarget() {{
                        const targetEl = doc.getElementById(targetId);
                        if (targetEl) {{
                            targetEl.scrollIntoView({{ behavior: scrollBehavior, block: 'start' }});
                            return true;
                        }}
                        return false;
                    }}

                    if (!jumpToTarget()) {{
                        const observer = new MutationObserver(() => {{
                            if (jumpToTarget()) {{
                                observer.disconnect();
                            }}
                        }});
                        observer.observe(doc.body, {{ childList: true, subtree: true }});

                        setTimeout(() => observer.disconnect(), 1500);
                    }}
                }})();
            </script>
            """,
            height=1,
            width=1,
        )

    # 4. Renderização Condicional da Página Selecionada
    if st.session_state.pagina == "dashboard":
        dashboard.renderizar(con.cursor())
    elif st.session_state.pagina == "simulador":
        simulador.renderizar(con.cursor())
    elif st.session_state.pagina == "relatorio":
        relatorios.renderizar(con.cursor())