import streamlit as st

# Dicionário de usuários padrão (mock)
USUARIOS_VALIDOS = {
    "admin@ecommerce.com": "123456",
    "gestor@ecommerce.com": "admin2026"
}

def renderizar():
    # Centraliza o formulário de login na tela
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.title("🔐 Acesso ao SAD E-commerce")
        st.subheader("Sistema de Apoio à Decisão de Marketing")
        st.write("Digite suas credenciais para acessar o painel.")
        
        with st.form("form_login"):
            usuario = st.text_input("E-mail", placeholder="seu.email@ecommerce.com")
            senha = st.text_input("Senha", type="password", placeholder="******")
            btn_entrar = st.form_submit_button("Entrar no Sistema", use_container_width=True)
            
            if btn_entrar:
                if usuario in USUARIOS_VALIDOS and USUARIOS_VALIDOS[usuario] == senha:
                    st.session_state['logado'] = True
                    st.session_state['usuario_atual'] = usuario
                    st.success("Login realizado com sucesso!")
                    st.rerun()  # Recarrega a página para redirecionar
                else:
                    st.error("Usuário ou senha incorretos.")
        
        # Dica visual para facilitar os testes (e para o professor!)
        st.info("💡 **Credenciais de teste:**\n- **Usuário:** `admin@ecommerce.com`\n- **Senha:** `123456`")