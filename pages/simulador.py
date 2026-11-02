import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler


def formata_br(valor, prefixo="", sufixo="", decimais=2):
    """Formata números para o padrão brasileiro (milhar com ponto, decimal com vírgula)."""
    if valor is None or pd.isna(valor):
        return "N/A"
    try:
        fmt = (
            f"{valor:,.{decimais}f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )
        return f"{prefixo}{fmt}{sufixo}"
    except Exception:
        return str(valor)


@st.cache_data(ttl=600)
def carregar_dados_rfm(_con):
    """Extrai e calcula as métricas de Recência, Frequência, Valor Monetário e Custo Médio por cliente a partir dos pedidos concluídos."""
    query = """
        WITH data_max AS (
            SELECT MAX(TRY_CAST(created_at AS DATE)) as max_date 
            FROM order_items 
            WHERE status = 'Complete'
        )
        SELECT 
            oi.user_id,
            DATEDIFF('day', MAX(TRY_CAST(oi.created_at AS DATE)), (SELECT max_date FROM data_max)) AS recencia,
            COUNT(DISTINCT oi.order_id) AS frequencia,
            SUM(oi.sale_price) AS valor_monetario,
            AVG(p.cost) AS custo_medio_produto,
            SUM(oi.sale_price - p.cost) AS lucro_total
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.status = 'Complete'
        GROUP BY oi.user_id
        HAVING SUM(oi.sale_price) > 0
    """
    df = _con.execute(query).df()
    return df


def aplicar_kmeans(df_rfm, n_clusters=4):
    """Aplica K-Means com k=4 e rotula os clusters dinamicamente por perfil estatístico alinhado à literatura de segmentação RFM (Fader et al., 2005)."""
    df = df_rfm.copy()
    X = df[["recencia", "frequencia", "valor_monetario"]]

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    df["cluster_id"] = kmeans.fit_predict(X_scaled)

    # Mapeamento de perfis estatísticos dos centroides
    perfil = (
        df.groupby("cluster_id")
        .agg(
            recencia_media=("recencia", "mean"),
            frequencia_media=("frequencia", "mean"),
            ticket_medio=(
                "valor_monetario",
                lambda x: (x / df.loc[x.index, "frequencia"]).mean(),
            ),
            valor_medio=("valor_monetario", "mean"),
        )
        .reset_index()
    )

    cluster_map = {}
    ids_restantes = list(perfil["cluster_id"])

    # 1. Cluster de Maior Ticket Médio -> High-Spenders
    id_ticket = int(perfil.loc[perfil["ticket_medio"].idxmax()]["cluster_id"])
    cluster_map[id_ticket] = "💰 Clientes de Alto-Valor"
    ids_restantes.remove(id_ticket)

    # 2. Cluster de Maior Recência (entre os restantes) -> Inativos / Hibernando
    perfil_r = perfil[perfil["cluster_id"].isin(ids_restantes)]
    id_inativo = int(perfil_r.loc[perfil_r["recencia_media"].idxmax()]["cluster_id"])
    cluster_map[id_inativo] = "💤 Clientes Inativos"
    ids_restantes.remove(id_inativo)

    # 3. Cluster de Maior Frequência (entre os restantes) -> Leais / Recorrentes
    perfil_f = perfil[perfil["cluster_id"].isin(ids_restantes)]
    id_leal = int(perfil_f.loc[perfil_f["frequencia_media"].idxmax()]["cluster_id"])
    cluster_map[id_leal] = "💜 Clientes Leais"
    ids_restantes.remove(id_leal)

    # 4. O último cluster vira Clientes Novos / Promissores
    if ids_restantes:
        cluster_map[int(ids_restantes[0])] = "🌱 Clientes Promissores"

    df["cluster_nome"] = df["cluster_id"].map(cluster_map)
    return df


def renderizar(con):
    st.header("🔮 Módulo de Simulação Preditiva & Clusterização de Clientes")
    st.markdown(
        """
        Este módulo utiliza o algoritmo de **Clusterização K-Means (k=4)** baseado no modelo **RFM (Recência, Frequência e Valor Monetário)** para segmentar a base de clientes e fornecer um **Simulador Preditivo de Marketing (Cenários "What-If")**.
        """
    )

    df_rfm = carregar_dados_rfm(con)
    if df_rfm.empty:
        st.warning(
            "Nenhum dado de pedido concluído encontrado para realizar a clusterização."
        )
        return

    # Aplicação do K-Means com k=4 fixo
    df_clustered = aplicar_kmeans(df_rfm, n_clusters=4)
    
    cores_clusters = {
        "💰 Clientes de Alto-Valor": "#F2B701",
        "💤 Clientes Inativos": "#3969AC",
        "💜 Clientes Leais": "#7F3C8D",
        "🌱 Clientes Promissores": "#11A579"
    }

    # ====================================================
    # SEÇÃO 1: VISUALIZAÇÃO E PERFIL DOS CLUSTERS (RFM)
    # ====================================================
    st.markdown("---")
    st.markdown("### 📊 1. Perfis de Segmentos de Clientes")

    resumo_clusters = (
        df_clustered.groupby("cluster_nome")
        .agg(
            Total_Clientes=("user_id", "count"),
            Recencia_Media=("recencia", "mean"),
            Frequencia_Media=("frequencia", "mean"),
            Ticket_Medio=(
                "valor_monetario",
                lambda x: (x / df_clustered.loc[x.index, "frequencia"]).mean(),
            ),
            Valor_Total=("valor_monetario", "sum"),
            Lucro_Total=("lucro_total", "sum"),
        )
        .reset_index()
        .sort_values("Valor_Total", ascending=False)
    )

    # Cartões de KPIs por Cluster
    cols = st.columns(len(resumo_clusters))
    for idx, row in resumo_clusters.reset_index(drop=True).iterrows():
        if idx < len(cols):
            with cols[idx]:
                st.metric(
                    label=row["cluster_nome"],
                    value=f"{int(row['Total_Clientes']):,}".replace(
                        ",", "."
                    )
                )

    # --- PAINEL TRIPLO DE GRÁFICOS (R, F, M) ---
    st.markdown("#### Perfil Comportamental Médio por Segmento")
    col_r, col_f, col_m = st.columns(3)

    with col_r:
        st.markdown("**1. Recência Média (Dias sem comprar)**")
        fig_r = px.bar(
            resumo_clusters,
            x="cluster_nome",
            y="Recencia_Media",
            color="cluster_nome",
            color_discrete_map=cores_clusters,
        )
        fig_r.update_traces(
            texttemplate="%{y:.1f}d", textposition="outside", cliponaxis=False
        )
        fig_r.update_layout(
            showlegend=False,
            xaxis_title="",
            yaxis_title="Dias",
            margin=dict(t=20, b=20, l=10, r=10),
            separators=",.",
        )
        st.plotly_chart(fig_r, use_container_width=True)

    with col_f:
        st.markdown("**2. Frequência Média (Nº Pedidos)**")
        fig_f = px.bar(
            resumo_clusters,
            x="cluster_nome",
            y="Frequencia_Media",
            color="cluster_nome",
            color_discrete_map=cores_clusters,
        )
        fig_f.update_traces(
            texttemplate="%{y:.2f}", textposition="outside", cliponaxis=False
        )
        fig_f.update_layout(
            showlegend=False,
            xaxis_title="",
            yaxis_title="Pedidos",
            margin=dict(t=20, b=20, l=10, r=10),
            separators=",.",
        )
        st.plotly_chart(fig_f, use_container_width=True)

    with col_m:
        st.markdown("**3. Ticket Médio (Valor p/ Pedido)**")
        fig_m = px.bar(
            resumo_clusters,
            x="cluster_nome",
            y="Ticket_Medio",
            color="cluster_nome",
            color_discrete_map=cores_clusters,
        )
        fig_m.update_traces(
            texttemplate="US$ %{y:.1f}", textposition="outside", cliponaxis=False
        )
        fig_m.update_layout(
            showlegend=False,
            xaxis_title="",
            yaxis_title="Valor (US$)",
            margin=dict(t=20, b=20, l=10, r=10),
            separators=",.",
        )
        st.plotly_chart(fig_m, use_container_width=True)

    # --- GRÁFICO DE PIZZA E TABELA DETALHADA ---
    col_pie, col_tab = st.columns([0.7, 1.3])

    with col_pie:
        st.markdown("**Participação no Faturamento Total**")
        fig_pie = px.pie(
            resumo_clusters,
            names="cluster_nome",
            values="Valor_Total",
            hole=0.4,
            color="cluster_nome",
            color_discrete_map=cores_clusters
        )
        fig_pie.update_traces(textinfo="percent+label", textposition="inside")
        fig_pie.update_layout(
            height=260,
            separators=",.",
            showlegend=False,
            margin=dict(t=10, b=10, l=10, r=10)
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_tab:
        st.markdown("**📋 Comparativo Detalhado por Segmento**")

        # 1. Copia e formata os dados
        df_trans = resumo_clusters.copy()
        df_trans["Total de Clientes"] = df_trans["Total_Clientes"].apply(
            lambda x: formata_br(x, decimais=0)
        )
        df_trans["Recência Média (Dias)"] = df_trans["Recencia_Media"].apply(
            lambda x: formata_br(x, decimais=1)
        )
        df_trans["Frequência Média (Pedidos)"] = df_trans["Frequencia_Media"].apply(
            lambda x: formata_br(x, decimais=2)
        )
        df_trans["Ticket Médio"] = df_trans["Ticket_Medio"].apply(
            lambda x: formata_br(x, prefixo="US$ ")
        )
        df_trans["Receita Total"] = df_trans["Valor_Total"].apply(
            lambda x: formata_br(x, prefixo="US$ ")
        )
        df_trans["Lucro Total"] = df_trans["Lucro_Total"].apply(
            lambda x: formata_br(x, prefixo="US$ ")
        )

        # 2. Transpõe a tabela para colocar cada Cluster em uma Coluna
        tabela_final = df_trans.set_index("cluster_nome")[
            [
                "Total de Clientes",
                "Recência Média (Dias)",
                "Frequência Média (Pedidos)",
                "Ticket Médio",
                "Receita Total",
                "Lucro Total",
            ]
        ].T
        st.dataframe(tabela_final, use_container_width=True)

    # ====================================================
    # SEÇÃO 2: SIMULADOR PREDITIVO DE MARKETING ("WHAT-IF")
    # ====================================================
    st.markdown("---")
    st.markdown("### 🎯 2. Simulador Preditivo de Campanhas de Marketing")
    st.markdown(
        """
        Configure as **alavancas de decisão** para simular o retorno financeiro aproximado e a viabilidade econômica de uma ação comercial direcionada a um segmento específico.
        """
    )

    col_sim1, col_sim2 = st.columns(2)
    opcoes_segmento = list(resumo_clusters["cluster_nome"].unique())

    with col_sim1:
        st.subheader("🛠️ Parâmetros da Simulação")
        segmento_alvo = st.selectbox("Escolha o Segmento Alvo:", opcoes_segmento)
        pct_conversao = st.slider(
            "Taxa de Recompra/Resposta Esperada (%)",
            min_value=1.0,
            max_value=50.0,
            value=15.0,
            step=0.5,
            help="Percentual de clientes do segmento que responderão positivamente à oferta.",
        )
        pct_desconto = st.slider(
            "Desconto / Incentivo Promocional (%)",
            min_value=0.0,
            max_value=30.0,
            value=10.0,
            step=1.0,
            help="Desconto concedido sobre o valor da compra.",
        )
        custo_fixo = st.number_input(
            "Custo Fixo da Campanha (US$)",
            min_value=0.0,
            max_value=50000.0,
            value=1000.0,
            step=100.0,
            help="Custo fixo de disparo (e-mail marketing, mídia paga, operacional).",
        )

    # Cálculos Preditivos em Tempo Real
    df_target = df_clustered[df_clustered["cluster_nome"] == segmento_alvo]
    n_clientes_target = len(df_target)
    ticket_medio_target = (
        df_target["valor_monetario"] / df_target["frequencia"]
    ).mean()
    custo_prod_medio_target = df_target["custo_medio_produto"].mean()

    clientes_impactados = int(n_clientes_target * (pct_conversao / 100.0))
    receita_bruta_proj = clientes_impactados * ticket_medio_target
    custo_desconto_total = receita_bruta_proj * (pct_desconto / 100.0)
    custo_total_campanha = custo_desconto_total + custo_fixo
    lucro_bruto_vendas = clientes_impactados * (
        ticket_medio_target - custo_prod_medio_target
    )
    lucro_liquido_proj = lucro_bruto_vendas - custo_total_campanha
    roi_proj = (
        (lucro_liquido_proj / custo_total_campanha * 100.0)
        if custo_total_campanha > 0
        else 0.0
    )

    # --- ORIENTAÇÃO NA COLUNA ESQUERDA (Preenche o espaço em branco) ---
    with col_sim1:
        st.markdown("---")
        st.markdown("#### 💡 Orientação para Tomada de Decisão")
        if lucro_liquido_proj > 0:
            st.success(
                f"""
                **Cenário Viável e Lucrativo!** A campanha projetada para o segmento **{segmento_alvo}** gera um lucro líquido incremental de **US$ {formata_br(lucro_liquido_proj)}** com retorno sobre o investimento de **{formata_br(roi_proj, decimais=1)}%**. A alocação de orçamento para esta ação é recomendada.
                """
            )
        else:
            st.error(
                f"""
                **Cenário Inviável (Déficit Financeiro)!** O desconto concedido (**{pct_desconto}%**) somado ao custo fixo de **US$ {formata_br(custo_fixo)}** consome toda a margem de contribuição gerada pelas vendas. **Ação Recomendada:** Reduza a taxa de desconto concedida ou aumente a meta de taxa de recompra esperada para reequilibrar o cenário.
                """
            )

    # --- RESULTADOS NA COLUNA DIREITA ---
    with col_sim2:
        st.subheader(f"📈 Resultado Projetado para: {segmento_alvo}")
        col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
        col_kpi1.metric(
            "Clientes Impactados", formata_br(clientes_impactados, decimais=0)
        )
        col_kpi2.metric(
            "Receita Bruta Incremental",
            formata_br(receita_bruta_proj, prefixo="US$ "),
        )
        col_kpi3.metric(
            "Custo Total da Campanha",
            formata_br(custo_total_campanha, prefixo="US$ "),
        )

        col_kpi4, col_kpi5 = st.columns(2)
        col_kpi4.metric(
            "Lucro Líquido Incremental",
            formata_br(lucro_liquido_proj, prefixo="US$ ")
        )
        col_kpi5.metric(
            "Retorno s/ Investimento (ROI)",
            f"{formata_br(roi_proj, decimais=1)}%",
        )

        df_sim_graph = pd.DataFrame(
            {
                "Métrica": ["Receita Bruta", "Custo Total", "Lucro Líquido"],
                "Valor (US$)": [
                    receita_bruta_proj,
                    custo_total_campanha,
                    lucro_liquido_proj,
                ],
            }
        )
        fig_sim = px.bar(
            df_sim_graph,
            x="Métrica",
            y="Valor (US$)",
            color="Métrica",
            color_discrete_map={
                "Receita Bruta": "#1b4d3e",
                "Custo Total": "#d97724",
                "Lucro Líquido": (
                    "#107c41" if lucro_liquido_proj >= 0 else "#c93b2b"
                ),
            },
            title="Demonstrativo de Resultado Simulado (DRE Incremental)",
        )
        fig_sim.update_traces(
            texttemplate="US$ %{y:.2s}", textposition="outside", cliponaxis=False
        )
        fig_sim.update_layout(
            separators=",.",
            showlegend=False,
            margin=dict(t=40, b=20, l=10, r=10),
        )
        st.plotly_chart(fig_sim, use_container_width=True)