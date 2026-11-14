import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

ORDEM_ALFABETICA_CLUSTERS = [
    "💰 Clientes de Alto-Valor",
    "💤 Clientes Inativos",
    "💜 Clientes Leais",
    "🌱 Clientes Promissores",
]


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
    """Extrai e calcula as métricas de Recência, Frequência, Valor Monetário e Custo Médio por cliente."""
    query = """
    WITH data_max AS (
        SELECT MAX(TRY_CAST(created_at AS DATE)) as max_date
        FROM order_items WHERE status = 'Complete'
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
    """Aplica K-Means e atribui rótulos com a ordenação categórica definida."""
    df = df_rfm.copy()
    X = df[["recencia", "frequencia", "valor_monetario"]]
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    df["cluster_id"] = kmeans.fit_predict(X_scaled)

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

    # 1. Maior Ticket -> Clientes de Alto-Valor
    id_ticket = int(perfil.loc[perfil["ticket_medio"].idxmax()]["cluster_id"])
    cluster_map[id_ticket] = "💰 Clientes de Alto-Valor"
    ids_restantes.remove(id_ticket)

    # 2. Maior Recência -> Inativos
    perfil_r = perfil[perfil["cluster_id"].isin(ids_restantes)]
    id_inativo = int(
        perfil_r.loc[perfil_r["recencia_media"].idxmax()]["cluster_id"]
    )
    cluster_map[id_inativo] = "💤 Clientes Inativos"
    ids_restantes.remove(id_inativo)

    # 3. Maior Frequência -> Leais
    perfil_f = perfil[perfil["cluster_id"].isin(ids_restantes)]
    id_leal = int(
        perfil_f.loc[perfil_f["frequencia_media"].idxmax()]["cluster_id"]
    )
    cluster_map[id_leal] = "💜 Clientes Leais"
    ids_restantes.remove(id_leal)

    # 4. Restante -> Promissores
    if ids_restantes:
        cluster_map[int(ids_restantes[0])] = "🌱 Clientes Promissores"

    df["cluster_nome"] = df["cluster_id"].map(cluster_map)

    # FORÇA A ORDENAÇÃO CATEGÓRICA DEFINIDA
    df["cluster_nome"] = pd.Categorical(
        df["cluster_nome"], categories=ORDEM_ALFABETICA_CLUSTERS, ordered=True
    )
    return df


def renderizar(con):
    st.header("🔮 Módulo de Simulação Preditiva & Clusterização de Clientes")
    st.markdown(
        "Este módulo combina **Clusterização K-Means (k=4)** baseada em **RFM** e um **Simulador Preditivo 'What-If'** com taxa de resposta ajustada por segmento."
    )
    
    if "val_tx_conversao" not in st.session_state:
        st.session_state["val_tx_conversao"] = 12.0
    if "val_pct_desconto" not in st.session_state:
        st.session_state["val_pct_desconto"] = 10.0
    if "val_custo_fixo" not in st.session_state:
        st.session_state["val_custo_fixo"] = 1000.0
    if "val_meta_romi" not in st.session_state:
        st.session_state["val_meta_romi"] = 4.0

    df_rfm = carregar_dados_rfm(con)
    if df_rfm.empty:
        st.warning("Nenhum dado encontrado para realizar a clusterização.")
        return

    df_clustered = aplicar_kmeans(df_rfm, n_clusters=4)

    cores_clusters = {
        "💰 Clientes de Alto-Valor": "#F2B701",
        "💤 Clientes Inativos": "#3969AC",
        "💜 Clientes Leais": "#7F3C8D",
        "🌱 Clientes Promissores": "#11A579",
    }

    # ====================================================
    # SEÇÃO 1: VISUALIZAÇÃO E PERFIL DOS CLUSTERS (ORDEM ALFABÉTICA)
    # ====================================================
    st.markdown("---")
    st.markdown("### 📊 Perfis de Segmentos de Clientes")

    # RESUMO ORDENADO PELA CATEGORIA ALFABÉTICA
    resumo_clusters = (
        df_clustered.groupby("cluster_nome", observed=False)
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
        .sort_values("cluster_nome")
    )

    # 1. Cards de métricas
    cols = st.columns(len(resumo_clusters))
    for idx, row in resumo_clusters.reset_index(drop=True).iterrows():
        if idx < len(cols):
            with cols[idx]:
                st.metric(
                    label=row["cluster_nome"],
                    value=f"{int(row['Total_Clientes']):,}".replace(",", "."),
                )

    # 2. Gráficos de Caracterização dos Clusters (Eixo X na Ordem Alfabética Explicita)
    st.markdown("#### Perfil Comportamental Médio por Segmento")
    col_r, col_f, col_m = st.columns(3)
    layout_eixo_x = dict(
        categoryorder="array", categoryarray=ORDEM_ALFABETICA_CLUSTERS
    )

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
            xaxis=layout_eixo_x,
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
            xaxis=layout_eixo_x,
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
            xaxis=layout_eixo_x,
            margin=dict(t=20, b=20, l=10, r=10),
            separators=",.",
        )
        st.plotly_chart(fig_m, use_container_width=True)

    # 3. Pizza de Faturamento e Tabela Resumo
    col_pie, col_tab = st.columns([0.7, 1.3])

    with col_pie:
        st.markdown("**Participação no Faturamento Total**")
        fig_pie = px.pie(
            resumo_clusters,
            names="cluster_nome",
            values="Valor_Total",
            hole=0.4,
            color="cluster_nome",
            color_discrete_map=cores_clusters,
        )
        fig_pie.update_traces(textinfo="percent+label", textposition="inside")
        fig_pie.update_layout(
            height=260,
            showlegend=False,
            margin=dict(t=10, b=10, l=10, r=10),
            separators=",.",
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_tab:
        st.markdown("**📋 Comparativo Detalhado por Segmento**")
        df_trans = resumo_clusters.copy()
        df_trans["Total de Clientes"] = df_trans["Total_Clientes"].apply(
            lambda x: formata_br(x, decimais=0)
        )
        df_trans["Recência Média (Dias)"] = df_trans["Recencia_Media"].apply(
            lambda x: formata_br(x, decimais=1)
        )
        df_trans["Frequência Média (Pedidos)"] = df_trans[
            "Frequencia_Media"
        ].apply(lambda x: formata_br(x, decimais=2))
        df_trans["Ticket Médio"] = df_trans["Ticket_Medio"].apply(
            lambda x: formata_br(x, prefixo="US$ ")
        )
        df_trans["Receita Total"] = df_trans["Valor_Total"].apply(
            lambda x: formata_br(x, prefixo="US$ ")
        )
        df_trans["Lucro Total"] = df_trans["Lucro_Total"].apply(
            lambda x: formata_br(x, prefixo="US$ ")
        )

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
    # SEÇÃO 2: SIMULADOR PREDITIVO (EXIBIÇÃO NA MESMA ORDEM)
    # ====================================================
    st.markdown("---")
    st.markdown("### 🎯 Simulador Preditivo de Campanhas de Marketing")
    st.markdown(
        "Configure as alavancas de decisão para calcular o retorno financeiro projetado e a viabilidade econômica por segmento:"
    )

    col_sim1, col_sim2 = st.columns([1.1, 1.9])

    with col_sim1:
        st.subheader("🛠️ Parâmetros da Simulação")
        tx_conversao_base = st.slider(
            "Taxa Média de Resposta Base (%)",
            1.0,
            40.0,
            value=st.session_state["val_tx_conversao"],
            step=0.5,
            key="input_tx_conversao",
            on_change=lambda: st.session_state.update(
                {"val_tx_conversao": st.session_state["input_tx_conversao"]}
            ),
            help="Taxa base de resposta. O modelo ajusta a conversão de cada cluster pela recência média do segmento.",
        )
        pct_desconto = st.slider(
            "Desconto Promocional (%)",
            0.0,
            30.0,
            value=st.session_state["val_pct_desconto"],
            step=1.0,
            key="input_pct_desconto",
            on_change=lambda: st.session_state.update(
                {"val_pct_desconto": st.session_state["input_pct_desconto"]}
            ),
            help="Desconto concedido sobre o valor do produto.",
        )
        custo_fixo = st.number_input(
            "Custo Fixo por Segmento (US$)",
            0.0,
            50000.0,
            value=st.session_state["val_custo_fixo"],
            step=100.0,
            key="input_custo_fixo",
            on_change=lambda: st.session_state.update(
                {"val_custo_fixo": st.session_state["input_custo_fixo"]}
            ),
            help="Custo fixo de disparo/mídia alocado por segmento.",
        )
        meta_romi = st.slider(
            "Meta de ROMI / Ratio (x:1)",
            1.5,
            10.0,
            value=st.session_state["val_meta_romi"],
            step=0.5,
            key="input_meta_romi",
            on_change=lambda: st.session_state.update(
                {"val_meta_romi": st.session_state["input_meta_romi"]}
            ),
            help="Proporção mínima de receita gerada para cada US$ 1 de custo investido.",
        )

    with col_sim2:
        st.subheader("🎯 Classificação de Impacto por Segmento")
        recencia_global = df_clustered["recencia"].mean()
        resultados_simulacao = []

        for _, row_cluster in resumo_clusters.iterrows():
            seg = str(row_cluster["cluster_nome"])
            df_target = df_clustered[df_clustered["cluster_nome"] == seg]

            n_clientes = len(df_target)
            ticket_medio = row_cluster["Ticket_Medio"]
            custo_prod = df_target["custo_medio_produto"].mean()
            recencia_seg = row_cluster["Recencia_Media"]

            # Ponderação da conversão por recência e elasticidade do desconto
            fator_recencia = np.exp(-0.5 * (recencia_seg / recencia_global))
            fator_promocional = 1.0 + (pct_desconto / 100.0) * 1.2

            taxa_conversao_efetiva = min(
                tx_conversao_base * fator_recencia * fator_promocional, 50.0
            )
            clientes_impactados = int(
                n_clientes * (taxa_conversao_efetiva / 100.0)
            )

            receita_bruta = clientes_impactados * ticket_medio
            custo_desconto = receita_bruta * (pct_desconto / 100.0)
            custo_total = custo_desconto + custo_fixo
            lucro_bruto = clientes_impactados * (ticket_medio - custo_prod)
            lucro_liquido = lucro_bruto - custo_total

            ratio_receita = (
                (receita_bruta / custo_total) if custo_total > 0 else 0.0
            )
            roi_proj = (
                (lucro_liquido / custo_total * 100.0) if custo_total > 0 else 0.0
            )

            # Classificação
            if lucro_liquido > 0 and ratio_receita >= meta_romi:
                class_label, badge_icon, cor_hex = "Bom", "🟢", "#5CB85C"
                justificativa = (
                    f"Cenário Altamente Recomendado! Resposta est. de {taxa_conversao_efetiva:.1f}%, "
                    f"gerando ROMI de {ratio_receita:.1f}:1 (meta: {meta_romi:.1f}:1) "
                    f"e Lucro Líquido de US$ {formata_br(lucro_liquido)}."
                )
            elif lucro_liquido > 0 and ratio_receita < meta_romi:
                class_label, badge_icon, cor_hex = "Médio", "🟡", "#F0AD4E"
                justificativa = (
                    f"Cenário Viável com Ressalva. Gera Lucro Líquido positivo de US$ {formata_br(lucro_liquido)}, "
                    f"mas o retorno ({ratio_receita:.1f}:1) fica abaixo da meta de {meta_romi:.1f}:1."
                )
            else:
                class_label, badge_icon, cor_hex = "Ruim", "🔴", "#D9534F"
                justificativa = (
                    f"Cenário Inviável! Custos promocionais e fixos superam a margem obtida, "
                    f"gerando prejuízo estimado de US$ {formata_br(lucro_liquido)}."
                )

            resultados_simulacao.append({
                "segmento": seg,
                "class_label": class_label,
                "badge_icon": badge_icon,
                "cor_hex": cor_hex,
                "justificativa": justificativa,
                "tx_efetiva": taxa_conversao_efetiva,
                "clientes_impactados": clientes_impactados,
                "receita_bruta": receita_bruta,
                "custo_total": custo_total,
                "lucro_liquido": lucro_liquido,
                "roi_proj": roi_proj,
                "ratio_receita": ratio_receita,
            })

        # ORDENAÇÃO EXPLÍCITA PELA LISTA DE CATEGORIAS
        resultados_simulacao.sort(
            key=lambda x: ORDEM_ALFABETICA_CLUSTERS.index(x["segmento"])
        )

        for res in resultados_simulacao:
            badge_html = f"{res['badge_icon']} {res['class_label']}"
            with st.expander(
                f"{res['segmento']} • {res['class_label']} ({res['badge_icon']})",
                expanded=False,
            ):
                st.markdown(
                    f"**Classificação:** {badge_html}", unsafe_allow_html=True
                )
                st.markdown(f"**Parecer da Simulação:** {res['justificativa']}")
                st.markdown("---")

                c1, c2, c3 = st.columns(3)
                c1.metric("Taxa Resposta Efetiva", f"{res['tx_efetiva']:.1f}%")
                c2.metric(
                    "Clientes Convertidos",
                    formata_br(res["clientes_impactados"], decimais=0),
                )
                c3.metric(
                    "Ratio de Receita (ROMI)", f"{res['ratio_receita']:.1f}:1"
                )

                c4, c5, c6 = st.columns(3)
                c4.metric(
                    "Receita Projetada",
                    formata_br(res["receita_bruta"], prefixo="US$ "),
                )
                c5.metric(
                    "Custo Total",
                    formata_br(res["custo_total"], prefixo="US$ "),
                )
                c6.metric(
                    "Lucro Líquido Proj.",
                    formata_br(res["lucro_liquido"], prefixo="US$ "),
                )

                df_sim_graph = pd.DataFrame({
                    "Métrica": ["Receita Bruta", "Custo Total", "Lucro Líquido"],
                    "Valor (US$)": [
                        res["receita_bruta"],
                        res["custo_total"],
                        res["lucro_liquido"],
                    ],
                })

                fig_sim = px.bar(
                    df_sim_graph,
                    x="Métrica",
                    y="Valor (US$)",
                    color="Métrica",
                    color_discrete_map={
                        "Receita Bruta": "#2B5C8F",
                        "Custo Total": "#D9534F",
                        "Lucro Líquido": (
                            "#5CB85C"
                            if res["lucro_liquido"] >= 0
                            else "#D9534F"
                        ),
                    },
                    title=f"Demonstrativo do Resultado Simulado: {res['segmento']}",
                )
                fig_sim.update_layout(
                    height=240,
                    showlegend=False,
                    margin=dict(l=20, r=20, t=35, b=20),
                )
                st.plotly_chart(fig_sim, use_container_width=True)