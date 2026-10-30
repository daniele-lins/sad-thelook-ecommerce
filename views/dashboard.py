import streamlit as st
import duckdb
import plotly.express as px
import pandas as pd
import datetime 


def renderizar(con):
    st.title("📊 Dashboard de Performance & Marketing")
    st.caption("Visão integrada de tráfego, funil de conversão, vendas e retenção")

    # ==========================================
    # 1. BARRA LATERAL - FILTROS GLOBAIS
    # ==========================================
    st.sidebar.markdown("---")
    st.sidebar.subheader("🎯 Filtros Globais")

    # Busca opções dinâmicas extraindo a string r[0] da tupla do fetchall()
    origens_raw = con.execute(
        "SELECT DISTINCT traffic_source FROM users WHERE traffic_source IS NOT NULL ORDER BY traffic_source"
    ).fetchall()
    origens = ["Todas as origens"] + [r[0] for r in origens_raw]

    paises_raw = con.execute(
        "SELECT DISTINCT country FROM users WHERE country IS NOT NULL ORDER BY country"
    ).fetchall()
    paises = ["Todos os locais"] + [r[0] for r in paises_raw]

    filtro_origem = st.sidebar.selectbox("Origem de tráfego", origens)
    
    # Consulta as menores e maiores datas existentes na base de dados 
    min_max_dates = con.execute(""" 
        SELECT 
            MIN(TRY_CAST(created_at AS DATE)), 
            MAX(TRY_CAST(created_at AS DATE)) 
        FROM events 
    """).fetchone()
    
    if min_max_dates and min_max_dates[0] and min_max_dates[1]:
        data_min = pd.to_datetime(min_max_dates[0]).date() 
        data_max = pd.to_datetime(min_max_dates[1]).date()
    else:
        data_min = datetime.date(2019, 1, 1)
        data_max = datetime.date(2024, 12, 31)
    
    # Seletor visual de calendário 
    intervalo_datas = st.sidebar.date_input( "Período do Filtro", value=(data_min, data_max), min_value=data_min, max_value=data_max, format="DD/MM/YYYY" )
    
    filtro_pais = st.sidebar.selectbox("País / Estado", paises)

    # Cláusulas WHERE dinâmicas
    where_events = []
    where_orders = []

    # 1. Filtro de Origem
    if filtro_origem != "Todas as origens":
        where_events.append(f"e.traffic_source = '{filtro_origem}'")
        where_orders.append(f"u.traffic_source = '{filtro_origem}'")

    # 2. Filtro de País
    if filtro_pais != "Todos os locais":
        where_events.append(f"u.country = '{filtro_pais}'")
        where_orders.append(f"u.country = '{filtro_pais}'")

    # 3. Filtro de Calendário (Garante que início e fim foram selecionados) 
    if isinstance(intervalo_datas, (list, tuple)) and len(intervalo_datas) == 2: 
        dt_inicio, dt_fim = intervalo_datas 
        where_events.append(f"TRY_CAST(e.created_at AS DATE) BETWEEN '{dt_inicio}' AND '{dt_fim}'") 
        where_orders.append(f"TRY_CAST(oi.created_at AS DATE) BETWEEN '{dt_inicio}' AND '{dt_fim}'")

    # Monta as strings de cláusula WHERE
    clause_ev = "WHERE " + " AND ".join(where_events) if where_events else ""
    clause_ord = "WHERE " + " AND ".join(where_orders) if where_orders else ""
    where_complete = (
        f"{clause_ord} AND oi.status = 'Complete'"
        if clause_ord
        else "WHERE oi.status = 'Complete'"
    )

    # ==========================================
    # 2. BIG NUMBERS (CARTÕES DE DESTAQUE)
    # ==========================================
    st.markdown("### 🔍 Topo e Meio de Funil")
    col_bn1, col_bn2, col_bn3 = st.columns(3)

    # Consultas de eventos com JOIN em users para permitir filtro de país
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

    col_bn1.metric(
        "Sessões Únicas",
        f"{q_sessoes/1000:.1f} mil" if q_sessoes >= 1000 else f"{q_sessoes}",
    )
    col_bn2.metric("Conversão Global", f"{tx_conversao:.2f}%")
    col_bn3.metric("Abandono de Carrinho", f"{tx_abandono:.2f}%")

    st.markdown("---")

    st.markdown("### 💰 Fundo de Funil e Retenção")
    c1, c2, c3, c4, c5 = st.columns(5)

    sql_fin = f"""
        SELECT 
            COALESCE(SUM(oi.sale_price), 0) AS receita, 
            COALESCE(SUM(oi.sale_price - p.cost), 0) AS lucro, 
            COUNT(DISTINCT oi.order_id) AS total_pedidos, 
            COUNT(DISTINCT oi.user_id) AS total_clientes 
        FROM order_items oi 
        JOIN products p ON oi.product_id = p.id 
        JOIN users u ON oi.user_id = u.id 
        {where_complete}
    """
    res_fin = con.execute(sql_fin).fetchone()

    # Extração correta dos elementos da tupla
    receita = res_fin[0] if res_fin else 0.0
    lucro = res_fin[1] if res_fin else 0.0
    pedidos = res_fin[2] if (res_fin and res_fin[2] > 0) else 1
    clientes = res_fin[3] if (res_fin and res_fin[3] > 0) else 1

    aov = receita / pedidos
    ltv = receita / clientes

    sql_recompra = f"""
        WITH compras AS ( 
            SELECT o.user_id, COUNT(DISTINCT o.order_id) as qtd 
            FROM orders o 
            JOIN users u ON o.user_id = u.id 
            JOIN order_items oi ON o.order_id = oi.order_id 
            {clause_ord} 
            GROUP BY o.user_id 
        ) 
        SELECT COALESCE(COUNT(CASE WHEN qtd > 1 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 0) 
        FROM compras
    """
    tx_recompra = con.execute(sql_recompra).fetchone()[0] or 0.0

    c1.metric(
        "Receita Total",
        f"US$ {receita/1e6:.2f} mi" if receita >= 1e6 else f"US$ {receita:,.2f}",
    )
    c2.metric(
        "Lucro Bruto",
        f"US$ {lucro/1e6:.2f} mi" if lucro >= 1e6 else f"US$ {lucro:,.2f}",
    )
    c3.metric("Ticket Médio (AOV)", f"US$ {aov:.2f}")
    c4.metric("LTV Médio", f"US$ {ltv:.2f}")
    c5.metric("Taxa de Recompra", f"{tx_recompra:.1f}%")

    st.markdown("---")

    # ==========================================
    # 3. SEÇÃO 1: TRÁFEGO E FUNIL
    # ==========================================
    st.subheader("🌐 Tráfego e Funil de Navegação")
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
                       "Página Inicial": "#76B5E7", 
                       "Departamento": "#76B5E7", 
                       "Produto": "#76B5E7", 
                       "Carrinho": "#d97724", # Destaque em Laranja 
                       "Compra": "#107c41", # Sucesso em Verde 
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
        fig_funnel.update_layout(margin=dict(l=20, r=20, t=20, b=20), showlegend=False)
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
        )
        st.plotly_chart(fig_conv, use_container_width=True)

    # ==========================================
    # 4. SEÇÃO 2: VENDAS, PRODUTOS E RETENÇÃO
    # ==========================================
    st.markdown("---")
    st.subheader("🛍️ Vendas, Produtos e Retenção")
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
        fig_canal.update_layout( 
            yaxis_title="Valor (US$)",
            xaxis_title="",
            legend_title_text="Métrica", # Ou use "" se quiser remover o título da legenda totalmente 
            margin=dict(t=30, b=20, l=10, r=10) 
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
                SUM(oi.sale_price) as Vendas 
            FROM order_items oi 
            JOIN products p ON oi.product_id = p.id 
            JOIN users u ON oi.user_id = u.id 
            {where_complete} 
            GROUP BY p.category 
            ORDER BY Vendas DESC 
            LIMIT 5
        """
        ).df()
        fig_cat = px.bar(
            df_cat,
            x="Vendas",
            y="Categoria",
            orientation="h",
            color_discrete_sequence=["#1b4d3e"],
        )
        fig_cat.update_traces(
            texttemplate="US$ %{x:,.0f}", textposition="outside"
        )
        fig_cat.update_layout(
            yaxis=dict(autorange="reversed"), xaxis_title="Vendas (US$)"
        )
        st.plotly_chart(fig_cat, use_container_width=True)

    with col_c2:
        df_brand = con.execute(
            f"""
            SELECT 
                p.brand as Marca, 
                SUM(oi.sale_price) as Vendas 
            FROM order_items oi 
            JOIN products p ON oi.product_id = p.id 
            JOIN users u ON oi.user_id = u.id 
            {where_complete} 
            GROUP BY p.brand 
            ORDER BY Vendas DESC 
            LIMIT 5
        """
        ).df()
        fig_brand = px.bar(
            df_brand,
            x="Vendas",
            y="Marca",
            orientation="h",
            color_discrete_sequence=["#2a7b62"],
        )
        fig_brand.update_traces(
            texttemplate="US$ %{x:,.0f}", textposition="outside"
        )
        fig_brand.update_layout(
            yaxis=dict(autorange="reversed"), xaxis_title="Vendas (US$)"
        )
        st.plotly_chart(fig_brand, use_container_width=True)