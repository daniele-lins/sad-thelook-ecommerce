import streamlit as st
import plotly.express as px
import pandas as pd
import datetime 

def formata_br(valor, prefixo="", sufixo="", decimais=2):
    """Formata números no padrão brasileiro: 1.234,56"""
    if valor is None:
        return "N/A"

    # 1. Formata no padrão americano inicial (1,234.56)
    texto = f"{valor:,.{decimais}f}"

    # 2. Inverte os separadores: vírgula vira ponto e ponto vira vírgula
    texto_br = texto.replace(",", "X").replace(".", ",").replace("X", ".")

    return f"{prefixo}{texto_br}{sufixo}"

def renderizar(con):
    st.title("📊 Dashboard de Performance & Marketing")
    st.caption("Visão integrada de tráfego, funil de conversão, vendas, retenção e segmentação de clientes")

    # ==========================================
    # 1. BARRA LATERAL - FILTROS GLOBAIS
    # ==========================================
    st.sidebar.markdown("---")
    st.sidebar.subheader("🎯 Filtros Globais")

    # --- 1. Filtro de Origem de Tráfego ---
    origens_raw = con.execute(
        "SELECT DISTINCT traffic_source FROM users WHERE traffic_source IS NOT NULL ORDER BY traffic_source"
    ).fetchall()
    origens = ["Todas as origens"] + [r[0] for r in origens_raw]
    filtro_origem = st.sidebar.selectbox("Origem de tráfego", origens)

    # --- 2. Filtro de Calendário ---
    min_max_dates = con.execute(
        "SELECT MIN(TRY_CAST(created_at AS DATE)), MAX(TRY_CAST(created_at AS DATE)) FROM order_items"
    ).fetchone()
    data_min = (
        pd.to_datetime(min_max_dates[0]).date()
        if (min_max_dates and min_max_dates[0])
        else datetime.date(2019, 1, 1)
    )
    data_max = (
        pd.to_datetime(min_max_dates[1]).date()
        if (min_max_dates and min_max_dates[1])
        else datetime.date(2024, 12, 31)
    )

    intervalo_datas = st.sidebar.date_input(
        "Período do Filtro",
        value=(data_min, data_max),
        min_value=data_min,
        max_value=data_max,
        format="DD/MM/YYYY",
    )

    # --- 3. Filtros Geográficos (País e Estado) ---
    paises_raw = con.execute(
        "SELECT DISTINCT country FROM users WHERE country IS NOT NULL ORDER BY country"
    ).fetchall()
    paises_disponiveis = [r[0] for r in paises_raw]
    paises_selecionados = st.sidebar.multiselect(
        "Países", options=paises_disponiveis, placeholder="Todos os países"
    )

    if paises_selecionados:
        placeholders = ", ".join(["?"] * len(paises_selecionados))
        sql_estados = f"""
            SELECT DISTINCT state 
            FROM users 
            WHERE country IN ({placeholders}) AND state IS NOT NULL 
            ORDER BY state
        """
        estados_raw = con.execute(sql_estados, paises_selecionados).fetchall()
    else:
        sql_estados = (
            "SELECT DISTINCT state FROM users WHERE state IS NOT NULL ORDER BY state"
        )
        estados_raw = con.execute(sql_estados).fetchall()

    estados_disponiveis = [r[0] for r in estados_raw]
    estados_selecionados = st.sidebar.multiselect(
        "Estados", options=estados_disponiveis, placeholder="Todos os estados"
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("👤 Filtros Demográficos")

    # --- 4. Filtro de Gênero ---
    genero_opcoes = {"Todos": None, "Feminino": "F", "Masculino": "M"}
    filtro_genero_rotulo = st.sidebar.radio(
        "Gênero do Cliente", list(genero_opcoes.keys()), horizontal=True
    )
    filtro_genero = genero_opcoes[filtro_genero_rotulo]

    # --- 5. Filtro de Faixa Etária (Slider) ---
    idade_min_max = con.execute("SELECT MIN(age), MAX(age) FROM users").fetchone()
    min_age_bd = (
        int(idade_min_max[0]) if (idade_min_max and idade_min_max[0]) else 12
    )
    max_age_bd = (
        int(idade_min_max[1]) if (idade_min_max and idade_min_max[1]) else 70
    )

    faixa_idade = st.sidebar.slider(
        "Faixa Etária (Anos)",
        min_value=min_age_bd,
        max_value=max_age_bd,
        value=(min_age_bd, max_age_bd),
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("📦 Filtros de Produto e Logística")
    # escrever observação embaixo do subheader bem pequenininho
    st.sidebar.caption("(Não altera dados de tráfego e funil)")

    # --- 6. Filtro de Categoria ---
    cats_raw = con.execute(
        "SELECT DISTINCT category FROM products WHERE category IS NOT NULL ORDER BY category"
    ).fetchall()
    cats_disponiveis = [r[0] for r in cats_raw]
    cats_selecionadas = st.sidebar.multiselect(
        "Categorias", options=cats_disponiveis, placeholder="Todas as categorias"
    )

    # --- 7. Filtro de Marca ---
    marcas_raw = con.execute(
        "SELECT DISTINCT brand FROM products WHERE brand IS NOT NULL ORDER BY brand"
    ).fetchall()
    marcas_disponiveis = [r[0] for r in marcas_raw]
    marcas_selecionadas = st.sidebar.multiselect(
        "Marcas", options=marcas_disponiveis, placeholder="Todas as marcas"
    )

    # --- 8. Filtro de Centro de Distribuição ---
    cds_raw = con.execute(
        "SELECT id, name FROM distribution_centers ORDER BY name"
    ).fetchall()
    cds_dict = {r[1]: r[0] for r in cds_raw}  # Mapeia Nome do CD -> ID do CD
    cds_selecionados = st.sidebar.multiselect(
        "Centro de Distribuição",
        options=list(cds_dict.keys()),
        placeholder="Todos os CDs",
    )

    # ==========================================
    # 2. MONTAGEM DAS CLÁUSULAS WHERE
    # ==========================================
    where_events = []
    where_orders = []
    where_u = []

    # 1. Filtro de Origem
    if filtro_origem != "Todas as origens":
        where_events.append(f"u.traffic_source = '{filtro_origem}'")
        where_orders.append(f"u.traffic_source = '{filtro_origem}'")
        where_u.append(f"u.traffic_source = '{filtro_origem}'")

    # 2. Filtro de Calendário
    if isinstance(intervalo_datas, (list, tuple)) and len(intervalo_datas) == 2:
        dt_inicio, dt_fim = intervalo_datas
        where_events.append(
            f"TRY_CAST(e.created_at AS DATE) BETWEEN '{dt_inicio}' AND '{dt_fim}'"
        )
        where_orders.append(
            f"TRY_CAST(oi.created_at AS DATE) BETWEEN '{dt_inicio}' AND '{dt_fim}'"
        )

    # 3. Filtros Geográficos
    if paises_selecionados:
        paises_limpos = [p.replace("'", "''") for p in paises_selecionados]
        paises_fmt = ", ".join([f"'{p}'" for p in paises_limpos])
        where_events.append(f"u.country IN ({paises_fmt})")
        where_orders.append(f"u.country IN ({paises_fmt})")
        where_u.append(f"u.country IN ({paises_fmt})")

    if estados_selecionados:
        estados_limpos = [e.replace("'", "''") for e in estados_selecionados]
        estados_fmt = ", ".join([f"'{e}'" for e in estados_limpos])
        where_events.append(f"u.state IN ({estados_fmt})")
        where_orders.append(f"u.state IN ({estados_fmt})")
        where_u.append(f"u.state IN ({estados_fmt})")

    # 4. Filtros Demográficos (Gênero e Idade)
    if filtro_genero:
        where_events.append(f"u.gender = '{filtro_genero}'")
        where_orders.append(f"u.gender = '{filtro_genero}'")
        where_u.append(f"u.gender = '{filtro_genero}'")

    # Correção do acesso às posições [0] e [1] da tupla
    if faixa_idade and (faixa_idade[0] > min_age_bd or faixa_idade[1] < max_age_bd):
        idade_min, idade_max = faixa_idade[0], faixa_idade[1]
        where_events.append(f"u.age BETWEEN {idade_min} AND {idade_max}")
        where_orders.append(f"u.age BETWEEN {idade_min} AND {idade_max}")
        where_u.append(f"u.age BETWEEN {idade_min} AND {idade_max}")

    # 5. Filtros Exclusivos de Produto / Estoque (APENAS na tabela de pedidos order_items)
    if cats_selecionadas:
        cats_limpas = [c.replace("'", "''") for c in cats_selecionadas]
        cats_fmt = ", ".join([f"'{c}'" for c in cats_limpas])
        where_orders.append(f"p.category IN ({cats_fmt})")

    if marcas_selecionadas:
        marcas_limpas = [m.replace("'", "''") for m in marcas_selecionadas]
        marcas_fmt = ", ".join([f"'{m}'" for m in marcas_limpas])
        where_orders.append(f"p.brand IN ({marcas_fmt})")

    if cds_selecionados:
        ids_cds = [str(cds_dict[nome]) for nome in cds_selecionados]
        ids_fmt = ", ".join(ids_cds)
        where_orders.append(f"p.distribution_center_id IN ({ids_fmt})")

    # Unificação das Cláusulas SQL
    clause_ev = "WHERE " + " AND ".join(where_events) if where_events else ""
    clause_ord = "WHERE " + " AND ".join(where_orders) if where_orders else ""
    where_complete = (
        f"{clause_ord} AND oi.status = 'Complete'"
        if clause_ord
        else "WHERE oi.status = 'Complete'"
    )

    # ==========================================
    # SEÇÃO 1: TRÁFEGO E FUNIL DE NAVEGAÇÃO
    # ==========================================
    st.subheader("🌐 Tráfego e Funil de Navegação")

    # --- Big Numbers do Funil ---
    col_bn1, col_bn2, col_bn3 = st.columns(3)

    q_sessoes = (
        con.execute(
            f"SELECT COUNT(DISTINCT e.session_id) FROM events e LEFT JOIN users u ON e.user_id = u.id {clause_ev}"
        ).fetchone()[0]
        or 0
    )

    w_pur = (
        f"{clause_ev} AND e.event_type = 'purchase'"
        if clause_ev
        else "WHERE e.event_type = 'purchase'"
    )
    q_compras = (
        con.execute(
            f"SELECT COUNT(DISTINCT e.session_id) FROM events e LEFT JOIN users u ON e.user_id = u.id {w_pur}"
        ).fetchone()[0]
        or 0
    )

    w_cart = (
        f"{clause_ev} AND e.event_type = 'cart'"
        if clause_ev
        else "WHERE e.event_type = 'cart'"
    )
    q_carrinho = (
        con.execute(
            f"SELECT COUNT(DISTINCT e.session_id) FROM events e LEFT JOIN users u ON e.user_id = u.id {w_cart}"
        ).fetchone()[0]
        or 0
    )

    tx_conversao = (q_compras / q_sessoes * 100) if q_sessoes > 0 else 0
    tx_abandono = (
        ((q_carrinho - q_compras) / q_carrinho * 100) if q_carrinho > 0 else 0
    )

    col_bn1.metric("Sessões Únicas", formata_br(q_sessoes, decimais=0))
    col_bn2.metric("Conversão Global", formata_br(tx_conversao, sufixo="%", decimais=2))
    col_bn3.metric("Abandono de Carrinho", formata_br(tx_abandono, sufixo="%", decimais=2))

    st.markdown("---")
    
    col_f1, col_f2 = st.columns(2)

    with col_f1:
        st.markdown("**Funil Completo do E-commerce**")
        
        df_funil = con.execute(
            f"""
            SELECT 
                CASE e.event_type
                    WHEN 'home' THEN 'Página Inicial'
                    WHEN 'department' THEN 'Departamento'
                    WHEN 'product' THEN 'Produto'
                    WHEN 'cart' THEN 'Carrinho'
                    WHEN 'purchase' THEN 'Compra'
                    WHEN 'cancel' THEN 'Cancelamento'
                END as "Etapa", 
                COUNT(DISTINCT e.session_id) as "Sessões"
            FROM events e 
            LEFT JOIN users u ON e.user_id = u.id 
            {clause_ev}
            GROUP BY e.event_type
        """
        ).df()
        cores_funil = { 
                       "Página Inicial": "#6bc7ad", 
                       "Departamento": "#6bc7ad", 
                       "Produto": "#6bc7ad", 
                       "Carrinho": "#2a7b62",
                       "Compra": "#1b4d3e", # Sucesso em Verde 
                       "Cancelamento": "#c93b2b" # Alerta em Vermelho 
                       }
        ordem_etapas = ["Página Inicial", "Departamento", "Produto", "Carrinho", "Compra", "Cancelamento"]
        fig_funnel = px.funnel(
            df_funil, 
            x="Sessões", 
            y="Etapa", 
            color="Etapa", 
            color_discrete_map=cores_funil,
            title=""
        )
        fig_funnel.update_yaxes(
            categoryorder="array",
            categoryarray=ordem_etapas,
            autorange="reversed"
        )
        fig_funnel.update_xaxes(visible=True, showticklabels=False, title_text="Quantidade de Sessões")
        fig_funnel.update_traces(texttemplate="%{x:,.0f}")
        fig_funnel.update_layout(margin=dict(l=20, r=20, t=20, b=20), showlegend=False, separators=",.")
        st.plotly_chart(fig_funnel, use_container_width=True)

    with col_f2:
        st.markdown("**Conversão por Origem de Tráfego**")
        df_conv_canal = con.execute(
            f"""
            SELECT 
                e.traffic_source as "Origem", 
                COUNT(DISTINCT CASE WHEN e.event_type = 'purchase' THEN e.session_id END) * 100.0 / NULLIF(COUNT(DISTINCT e.session_id), 0) as "Taxa de Conversão" 
            FROM events e 
            LEFT JOIN users u ON e.user_id = u.id 
            {clause_ev} 
            GROUP BY 1
            ORDER BY 1
        """
        ).df()
        fig_conv = px.bar(
            df_conv_canal,
            x="Origem",
            y="Taxa de Conversão",
            color_discrete_sequence=["#1b4d3e"],
        )
        fig_conv.update_traces(texttemplate="%{y:.2f}%", textposition="outside")
        fig_conv.update_layout(
            yaxis_title="Taxa de Conversão (%)",
            xaxis_title="",
            margin=dict(t=30, b=20, l=10, r=10),
            separators=",."
        )
        st.plotly_chart(fig_conv, use_container_width=True)

    # ==========================================
    # SEÇÃO 2: DESEMPENHO FINANCEIRO E VENDAS
    # ==========================================
    st.markdown("---")
    st.subheader("💰 Desempenho Financeiro e Vendas")

    # --- Big Numbers Financeiros ---
    c_f1, c_f2, c_f3 = st.columns(3)

    sql_fin = f"""
        SELECT 
            COALESCE(SUM(oi.sale_price), 0) AS receita, 
            COALESCE(SUM(oi.sale_price - p.cost), 0) AS lucro, 
            COUNT(DISTINCT oi.order_id) AS total_pedidos 
        FROM order_items oi 
        JOIN products p ON oi.product_id = p.id 
        JOIN users u ON oi.user_id = u.id 
        {where_complete}
    """
    res_fin = con.execute(sql_fin).fetchone()

    receita = res_fin[0] if res_fin else 0.0
    lucro = res_fin[1] if res_fin else 0.0
    pedidos = res_fin[2] if (res_fin and res_fin[2] > 0) else 1

    aov = receita / pedidos

    c_f1.metric("Receita Total", formata_br(receita, prefixo="US$ ", decimais=2))
    c_f2.metric("Lucro Bruto", formata_br(lucro, prefixo="US$ ", decimais=2))
    c_f3.metric("Ticket Médio (AOV)", formata_br(aov, prefixo="US$ ", decimais=2))

    st.markdown("---")

    col_v1, col_v2 = st.columns(2)

    with col_v1:
        st.markdown("**Receita vs. Lucro Bruto por Canal**")
        df_canal = con.execute(
            f"""
            SELECT 
                u.traffic_source as Canal, 
                SUM(oi.sale_price) as Receita, 
                SUM(oi.sale_price - p.cost) as Lucro 
            FROM order_items oi 
            JOIN products p ON oi.product_id = p.id 
            JOIN users u ON oi.user_id = u.id 
            {where_complete} 
            GROUP BY u.traffic_source
        """
        ).df()
        fig_canal = px.bar(
            df_canal,
            x="Canal",
            y=["Receita", "Lucro"],
            barmode="group",
            color_discrete_sequence=["#0e382c", "#d97724"],
            labels={"value": "Valor (US$)", "variable": "Métrica"} # Mapeia os nomes padrão
        )
        fig_canal.update_traces(texttemplate="US$ %{y:.2s}", textposition="outside", cliponaxis=False)
        fig_canal.update_layout( 
            yaxis_title="Valor (US$)",
            xaxis_title="",
            legend_title_text="Métrica", # Ou use "" se quiser remover o título da legenda totalmente 
            margin=dict(t=50, b=20, l=10, r=10) ,
            separators=",."
        )
        st.plotly_chart(fig_canal, use_container_width=True)

    with col_v2:
        st.markdown("**Evolução do Faturamento por Canal**")
        df_evo = con.execute(
            f"""
            SELECT 
                DATE_TRUNC('month', TRY_CAST(oi.created_at AS TIMESTAMP)) as "Mês", 
                u.traffic_source as Canal, 
                SUM(oi.sale_price) as Receita 
            FROM order_items oi 
            JOIN products p ON oi.product_id = p.id 
            JOIN users u ON oi.user_id = u.id 
            {where_complete} 
            GROUP BY "Mês", u.traffic_source 
            ORDER BY "Mês"
        """
        ).df()
        fig_evo = px.line(df_evo, x="Mês", y="Receita", color="Canal")
        fig_evo.update_layout(xaxis_title="Mês", yaxis_title="Receita (US$)")
        st.plotly_chart(fig_evo, use_container_width=True)

    # Categorias e Marcas Campeãs
    st.markdown("**Categorias e Marcas Campeãs**")
    col_c1, col_c2 = st.columns(2)

    with col_c1:
        df_cat = con.execute(
            f"""
            SELECT 
                p.category as Categoria, 
                SUM(oi.sale_price) as Receita 
            FROM order_items oi 
            JOIN products p ON oi.product_id = p.id 
            JOIN users u ON oi.user_id = u.id 
            {where_complete} 
            GROUP BY p.category 
            ORDER BY Receita DESC 
            LIMIT 5
        """
        ).df()
        fig_cat = px.bar(
            df_cat,
            x="Receita",
            y="Categoria",
            orientation="h",
            color_discrete_sequence=["#1b4d3e"],
        )
        fig_cat.update_traces(
            texttemplate="US$ %{x:,.0f}", textposition="outside", cliponaxis=False
        )
        fig_cat.update_layout(
            yaxis=dict(autorange="reversed"), xaxis_title="Receita (US$)", margin=dict(t=20, b=20, l=10, r=80), separators=",."
        )
        st.plotly_chart(fig_cat, use_container_width=True)

    with col_c2:
        df_brand = con.execute(
            f"""
            SELECT 
                p.brand as Marca, 
                SUM(oi.sale_price) as Receita 
            FROM order_items oi 
            JOIN products p ON oi.product_id = p.id 
            JOIN users u ON oi.user_id = u.id 
            {where_complete} 
            GROUP BY p.brand 
            ORDER BY Receita DESC 
            LIMIT 5
        """
        ).df()
        fig_brand = px.bar(
            df_brand,
            x="Receita",
            y="Marca",
            orientation="h",
            color_discrete_sequence=["#2a7b62"],
        )
        fig_brand.update_traces(
            texttemplate="US$ %{x:,.0f}", textposition="outside", cliponaxis=False
        )
        fig_brand.update_layout(
            yaxis=dict(autorange="reversed"), xaxis_title="Receita (US$)", margin=dict(t=20, b=20, l=10, r=80), separators=",."
        )
        st.plotly_chart(fig_brand, use_container_width=True)
    
    # ==========================================
    # SEÇÃO 3: RETENÇÃO E VALOR DE LONGO PRAZO
    # ==========================================
    st.markdown("---")
    st.subheader("🔄 Retenção e Valor de Longo Prazo")

    # --- 1. Big Numbers ---
    c_r1, c_r2 = st.columns(2)

    sql_ltv = f"""
        SELECT 
            COALESCE(SUM(oi.sale_price) / NULLIF(COUNT(DISTINCT oi.user_id), 0), 0) 
        FROM order_items oi 
        JOIN products p ON oi.product_id = p.id 
        JOIN users u ON oi.user_id = u.id 
        {where_complete}
    """
    ltv = con.execute(sql_ltv).fetchone()[0] or 0.0

    sql_recompra = f"""
        WITH compras AS ( 
            SELECT 
                oi.user_id, 
                COUNT(DISTINCT oi.order_id) as qtd 
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id 
            JOIN users u ON oi.user_id = u.id
            {where_complete} 
            GROUP BY oi.user_id 
        ) 
        SELECT 
            COALESCE(COUNT(CASE WHEN qtd > 1 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 0) 
        FROM compras
    """
    tx_recompra = con.execute(sql_recompra).fetchone()[0] or 0.0

    c_r1.metric("LTV Médio por Cliente", formata_br(ltv, prefixo="US$ ", decimais=2))
    c_r2.metric("Taxa de Recompra (Fidelidade)", formata_br(tx_recompra, sufixo="%", decimais=2))

    st.markdown("---")

    # --- 2. Gráficos de Retenção ---
    col_ret1, col_ret2 = st.columns(2)

    # Gráfico 1: Frequência de Compras por Cliente
    with col_ret1:
        st.markdown("**Frequência de Compras por Cliente**")
        df_freq = con.execute(
            f"""
            WITH contagem AS ( 
                SELECT 
                    oi.user_id, 
                    COUNT(DISTINCT oi.order_id) as total_pedidos 
                FROM order_items oi
                JOIN products p ON oi.product_id = p.id  
                JOIN users u ON oi.user_id = u.id 
                {where_complete} 
                GROUP BY oi.user_id 
            ) 
            SELECT 
                CASE 
                    WHEN total_pedidos = 1 THEN '1 pedido' 
                    WHEN total_pedidos = 2 THEN '2 pedidos' 
                    WHEN total_pedidos BETWEEN 3 AND 5 THEN '3 a 5 pedidos' 
                    ELSE '6+ pedidos' 
                END AS "Faixa de Pedidos", 
                COUNT(user_id) AS "Clientes" 
            FROM contagem 
            GROUP BY 1 
            ORDER BY 
                CASE "Faixa de Pedidos" 
                    WHEN '1 pedido' THEN 1 
                    WHEN '2 pedidos' THEN 2 
                    WHEN '3 a 5 pedidos' THEN 3 
                    ELSE 4 
                END
        """
        ).df()

        fig_freq = px.bar(
            df_freq,
            x="Faixa de Pedidos",
            y="Clientes",
            color_discrete_sequence=["#0e382c"],
        )
        fig_freq.update_traces(texttemplate="%{y:,.0f}", textposition="outside")
        fig_freq.update_layout(
            xaxis_title="",
            yaxis_title="Clientes",
            margin=dict(t=30, b=20, l=10, r=10),
            separators=",."
        )
        st.plotly_chart(fig_freq, use_container_width=True)

    # Gráfico 2: LTV Médio por Canal de Tráfego
    with col_ret2:
        st.markdown("**LTV Médio por Canal de Origem**")
        
        df_ltv_canal = con.execute(
            f"""
            SELECT 
                u.traffic_source AS "Canal", 
                ROUND(SUM(oi.sale_price) / NULLIF(COUNT(DISTINCT oi.user_id), 0), 2) AS "LTV" 
            FROM order_items oi 
            JOIN products p ON oi.product_id = p.id 
            JOIN users u ON oi.user_id = u.id 
            {where_complete} 
            GROUP BY u.traffic_source 
            ORDER BY LTV DESC
        """
        ).df()

        fig_ltv_canal = px.bar(
            df_ltv_canal,
            x="LTV",
            y="Canal",
            orientation="h",
            color_discrete_sequence=["#d97724"],
        )

        # 1. Adicionado cliponaxis=False para impedir que o rótulo seja cortado
        fig_ltv_canal.update_traces(
            texttemplate="US$ %{x:.2f}",
            textposition="outside",
            cliponaxis=False,
        )

        # 2. Aumentada a margem direita (r=80) para dar folga ao texto na tela
        fig_ltv_canal.update_layout(
            yaxis=dict(autorange="reversed"),
            xaxis_title="LTV Médio (US$)",
            margin=dict(t=20, b=20, l=10, r=80),
            separators=",."
        )

        st.plotly_chart(fig_ltv_canal, use_container_width=True)
        
    # ==========================================
    # SEÇÃO 4: PERFIL E SEGMENTAÇÃO DE CLIENTES
    # ==========================================
    st.markdown("---")
    st.subheader("👥 Perfil e Segmentação de Clientes")

   # --- Cartões de Destaque Demográficos Corrigidos ---
    col_p1, col_p2, col_p3 = st.columns(3)

    sql_demo_kpi = f"""
        SELECT 
            COUNT(DISTINCT u.id) as total_usuarios, 
            ROUND(AVG(u.age), 1) as idade_media, 
            COUNT(DISTINCT CASE WHEN u.gender = 'F' THEN u.id END) as total_f, 
            COUNT(DISTINCT CASE WHEN u.gender = 'M' THEN u.id END) as total_m 
        FROM users u 
        JOIN order_items oi ON u.id = oi.user_id 
        JOIN products p ON oi.product_id = p.id 
        {where_complete}
    """
    res_demo = con.execute(sql_demo_kpi).fetchone()

    total_usr = res_demo[0] if (res_demo and res_demo[0]) else 0
    idade_med = res_demo[1] if (res_demo and res_demo[1]) else 0.0
    total_f = res_demo[2] if (res_demo and res_demo[2]) else 0
    total_m = res_demo[3] if (res_demo and res_demo[3]) else 0

    # Lógica de decisão baseada em clientes únicos
    if total_f > total_m:
        gen_mode = "Feminino"
    elif total_m > total_f:
        gen_mode = "Masculino"
    else:
        gen_mode = "Empate"

    col_p1.metric("Total de Clientes", formata_br(total_usr, decimais=0))
    col_p2.metric("Idade Média do Público", f"{formata_br(idade_med, decimais=1)} anos")
    col_p3.metric("Gênero Predominante", gen_mode)

    st.markdown("---")

    # --- Gráficos Demográficos ---
    col_d1, col_d2 = st.columns(2)

    # 1. Faixa Etária
    with col_d1:
        st.markdown("**Distribuição por Faixa Etária**")
        df_age = con.execute(
            f"""
            SELECT 
                CASE 
                    WHEN u.age < 18 THEN 'Menor que 18' 
                    WHEN u.age BETWEEN 18 AND 25 THEN '18-25 anos' 
                    WHEN u.age BETWEEN 26 AND 35 THEN '26-35 anos' 
                    WHEN u.age BETWEEN 36 AND 50 THEN '36-50 anos' 
                    WHEN u.age BETWEEN 51 AND 65 THEN '51-65 anos' 
                    ELSE '65+ anos' 
                END AS "Faixa Etária", 
                COUNT(DISTINCT u.id) AS "Clientes" 
            FROM users u
            JOIN order_items oi ON oi.user_id = u.id
            JOIN products p ON oi.product_id = p.id
            {where_complete} 
            GROUP BY 1 
            ORDER BY 
                CASE "Faixa Etária" 
                    WHEN 'Menor que 18' THEN 1 
                    WHEN '18-25 anos' THEN 2 
                    WHEN '26-35 anos' THEN 3 
                    WHEN '36-50 anos' THEN 4 
                    WHEN '51-65 anos' THEN 5 
                    ELSE 6 
                END
        """
        ).df()

        fig_age = px.bar(
            df_age,
            x="Faixa Etária",
            y="Clientes",
            color_discrete_sequence=["#1b4d3e"],
        )
        fig_age.update_traces(texttemplate="%{y:,.0f}", textposition="outside")
        fig_age.update_layout(
            xaxis_title="",
            yaxis_title="Clientes",
            margin=dict(t=30, b=20, l=10, r=10),
            separators=",."
        )
        st.plotly_chart(fig_age, use_container_width=True)

    # 2. Distribuição por Gênero
    with col_d2:
        st.markdown("**Proporção de Clientes por Gênero**")
        df_gender = con.execute(
            f"""
            SELECT 
                CASE u.gender 
                    WHEN 'F' THEN 'Feminino' 
                    WHEN 'M' THEN 'Masculino' 
                    ELSE u.gender 
                END AS "Gênero", 
                COUNT(DISTINCT u.id) AS "Clientes" 
            FROM users u
            JOIN order_items oi ON oi.user_id = u.id
            JOIN products p ON oi.product_id = p.id
            {where_complete} 
            GROUP BY 1
        """
        ).df()

        fig_gender = px.pie(
            df_gender,
            names="Gênero",
            values="Clientes",
            hole=0.4,
            color="Gênero",
            color_discrete_map={"Feminino": "#d97724", "Masculino": "#1b4d3e"},
        )
        fig_gender.update_traces(textinfo="percent+label")
        fig_gender.update_layout(
            showlegend=False, margin=dict(t=20, b=20, l=10, r=10), separators=",."
        )
        st.plotly_chart(fig_gender, use_container_width=True)

    # 3. Concentração Geográfica
    st.markdown("**Principais Mercados (Top Países com Mais Clientes)**")
    df_geo = con.execute(
        f"""
        SELECT 
            u.country AS "País", 
            COUNT(DISTINCT u.id) AS "Clientes" 
        FROM users u
        JOIN order_items oi ON oi.user_id = u.id
        JOIN products p ON oi.product_id = p.id
        {where_complete} 
        GROUP BY 1 
        ORDER BY Clientes DESC 
        LIMIT 8
    """
    ).df()

    fig_geo = px.bar(
        df_geo,
        x="Clientes",
        y="País",
        orientation="h",
        color_discrete_sequence=["#2a7b62"],
    )
    fig_geo.update_traces(texttemplate="%{x:,.0f}", textposition="outside")
    fig_geo.update_layout(
        yaxis=dict(autorange="reversed"),
        xaxis_title="Total de Clientes",
        margin=dict(t=20, b=20, l=10, r=10),
        separators=",."
    )
    st.plotly_chart(fig_geo, use_container_width=True)