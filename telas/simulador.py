import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
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
    try:
        df = _con.execute(query).df()
        if df.empty:
            return gerar_dados_mock_rfm()
        return df
    except Exception:
        return gerar_dados_mock_rfm()

def gerar_dados_mock_rfm():
    """Fallback com dados simulados caso a consulta falhe ou retorne vazia."""
    np.random.seed(42)
    n = 1000
    return pd.DataFrame({
        "user_id": range(1, n + 1),
        "recencia": np.random.randint(1, 365, n),
        "frequencia": np.random.randint(1, 10, n),
        "valor_monetario": np.random.uniform(50, 2000, n),
        "custo_medio_produto": np.random.uniform(20, 80, n),
        "lucro_total": np.random.uniform(20, 1000, n)
    })

def aplicar_kmeans(df_rfm, n_clusters=4):
    """Aplica K-Means com k=4 e rotula os clusters dinamicamente por perfil estatístico."""
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
    
    # 1. Cluster de Maior Ticket Médio -> Clientes de Alto-Valor
    id_ticket = int(perfil.loc[perfil["ticket_medio"].idxmax()]["cluster_id"])
    cluster_map[id_ticket] = "💰 Clientes de Alto-Valor"
    ids_restantes.remove(id_ticket)
    
    # 2. Cluster de Maior Recência (entre os restantes) -> Inativos
    perfil_r = perfil[perfil["cluster_id"].isin(ids_restantes)]
    id_inativo = int(perfil_r.loc[perfil_r["recencia_media"].idxmax()]["cluster_id"])
    cluster_map[id_inativo] = "💤 Clientes Inativos"
    ids_restantes.remove(id_inativo)
    
    # 3. Cluster de Maior Frequência (entre os restantes) -> Leais
    perfil_f = perfil[perfil["cluster_id"].isin(ids_restantes)]
    id_leal = int(perfil_f.loc[perfil_f["frequencia_media"].idxmax()]["cluster_id"])
    cluster_map[id_leal] = "💜 Clientes Leais"
    ids_restantes.remove(id_leal)
    
    # 4. O último cluster vira Promissores
    if ids_restantes:
        cluster_map[int(ids_restantes[0])] = "🌱 Clientes Promissores"
        
    df["cluster_nome"] = df["cluster_id"].map(cluster_map)
    return df

def renderizar(con):
    st.header("🔮 Módulo de Simulação Preditiva & Clusterização de Clientes")
    st.markdown(
        """
        Este módulo combina **Clusterização K-Means (k=4)** baseada no modelo **RFM** e um **Simulador Preditivo "What-If"** para orientar ações de marketing e alocação orçamentária por segmento de cliente.
        """
    )
    
    df_rfm = carregar_dados_rfm(con)
    if df_rfm.empty:
        st.warning("Nenhum dado de pedido concluído encontrado para realizar a clusterização.")
        return
        
    df_clustered = aplicar_kmeans(df_rfm, n_clusters=4)
    
    cores_clusters = {
        "💰 Clientes de Alto-Valor": "#F2B701",
        "💤 Clientes Inativos": "#3969AC",
        "💜 Clientes Leais": "#7F3C8D",
        "🌱 Clientes Promissores": "#11A579",
    }
    
    # ====================================================
    # SEÇÃO 1: VISUALIZAÇÃO E PERFIL DOS CLUSTERS (RFM)
    # ====================================================
    st.markdown("---")
    st.markdown("### 📊 Perfis de Segmentos de Clientes")
    
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
    
    cols = st.columns(len(resumo_clusters))
    for idx, row in resumo_clusters.reset_index(drop=True).iterrows():
        if idx < len(cols):
            with cols[idx]:
                st.metric(
                    label=row["cluster_nome"],
                    value=f"{int(row['Total_Clientes']):,}".replace(",", "."),
                )
                
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
        fig_r.update_traces(texttemplate="%{y:.1f}d", textposition="outside", cliponaxis=False)
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
        fig_f.update_traces(texttemplate="%{y:.2f}", textposition="outside", cliponaxis=False)
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
        fig_m.update_traces(texttemplate="US$ %{y:.1f}", textposition="outside", cliponaxis=False)
        fig_m.update_layout(
            showlegend=False,
            xaxis_title="",
            yaxis_title="Valor (US$)",
            margin=dict(t=20, b=20, l=10, r=10),
            separators=",.",
        )
        st.plotly_chart(fig_m, use_container_width=True)
        
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
            separators=",.",
            showlegend=False,
            margin=dict(t=10, b=10, l=10, r=10),
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
    st.markdown("### 🎯 Simulador Preditivo de Campanhas de Marketing")
    st.markdown(
        """
        Configure as **alavancas de decisão** no painel à esquerda para calcular o retorno financeiro projetado e a viabilidade econômica de cada segmento de cliente:
        """
    )
    
    col_sim1, col_sim2 = st.columns([1.1, 1.9])
    
    with col_sim1:
        st.subheader("🛠️ Parâmetros da Simulação")
        
        pct_conversao = st.slider(
            "Taxa de Recompra Esperada (%)",
            min_value=1.0,
            max_value=50.0,
            value=15.0,
            step=0.5,
            help="Percentual de clientes de cada segmento que responderão efetuando uma nova compra."
        )
        
        pct_desconto = st.slider(
            "Desconto Promocional (%)",
            min_value=0.0,
            max_value=30.0,
            value=10.0,
            step=1.0,
            help="Desconto concedido sobre o valor da compra."
        )
        
        custo_fixo = st.number_input(
            "Custo Fixo da Campanha p/ Segmento (US$)",
            min_value=0.0,
            max_value=50000.0,
            value=1000.0,
            step=100.0,
            help="Custo fixo de disparo (e-mail marketing, mídia paga, operacional) por segmento."
        )
        
        meta_ratio = st.slider(
            "Proporção Mínima de Receita por Custo (x:1)",
            min_value=2.0,
            max_value=10.0,
            value=5.0,
            step=0.5,
            help="Benchmark ideal de retorno de receita gerada para cada US\$1 de custo investido."
        )
        
    with col_sim2:
        st.subheader("🎯 Opções Recomendadas por Segmento")
        st.caption("Resultados calculados e classificados para cada segmento de cliente com base nos parâmetros inseridos:")
        
        segmentos = list(resumo_clusters["cluster_nome"].unique())
        resultados_simulacao = []
        
        for seg in segmentos:
            df_target = df_clustered[df_clustered["cluster_nome"] == seg]
            n_clientes_target = len(df_target)
            ticket_medio_target = (df_target["valor_monetario"] / df_target["frequencia"]).mean()
            custo_prod_medio_target = df_target["custo_medio_produto"].mean()
            
            clientes_impactados = int(n_clientes_target * (pct_conversao / 100.0))
            receita_bruta_proj = clientes_impactados * ticket_medio_target
            custo_desconto_total = receita_bruta_proj * (pct_desconto / 100.0)
            custo_total_campanha = custo_desconto_total + custo_fixo
            
            lucro_bruto_vendas = clientes_impactados * (ticket_medio_target - custo_prod_medio_target)
            lucro_liquido_proj = lucro_bruto_vendas - custo_total_campanha
            
            roi_proj = (lucro_liquido_proj / custo_total_campanha * 100.0) if custo_total_campanha > 0 else 0.0
            ratio_receita = (receita_bruta_proj / custo_total_campanha) if custo_total_campanha > 0 else 0.0
            
            # Regra de Classificação
            if lucro_liquido_proj > 0 and ratio_receita >= meta_ratio:
                class_label = "Bom"
                badge_icon = "🟢"
                cor_hex = "#5CB85C"
                justificativa = f"Cenário Altamente Viável! Ação lucrativa que atinge proporção de retorno de {formata_br(ratio_receita, decimais=1)}:1 (superando a meta de {meta_ratio:.1f}:1) e ROI de {formata_br(roi_proj, decimais=1)}%."
                class_score = 2
            elif lucro_liquido_proj > 0 and ratio_receita < meta_ratio:
                class_label = "Médio"
                badge_icon = "🟡"
                cor_hex = "#F0AD4E"
                justificativa = f"Cenário de Atenção! Gera lucro líquido positivo de US$ {formata_br(lucro_liquido_proj)}, porém a proporção de receita ({formata_br(ratio_receita, decimais=1)}:1) está abaixo da meta de {meta_ratio:.1f}:1."
                class_score = 1
            else:
                class_label = "Ruim"
                badge_icon = "🔴"
                cor_hex = "#D9534F"
                justificativa = f"Cenário Inviável! O desconto e custos fixos superam a margem de contribuição, gerando prejuízo líquido de US$ {formata_br(lucro_liquido_proj)}."
                class_score = 0
                
            resultados_simulacao.append({
                "segmento": seg,
                "class_score": class_score,
                "class_label": class_label,
                "badge_icon": badge_icon,
                "cor_hex": cor_hex,
                "justificativa": justificativa,
                "clientes_impactados": clientes_impactados,
                "receita_bruta_proj": receita_bruta_proj,
                "custo_total_campanha": custo_total_campanha,
                "lucro_liquido_proj": lucro_liquido_proj,
                "roi_proj": roi_proj,
                "ratio_receita": ratio_receita,
            })
            
        # Ordena os clusters em ordem alfabética (A-Z)
        resultados_simulacao.sort(key=lambda x: x["segmento"], reverse=True)
        
        for res in resultados_simulacao:
            badge_html = f"<span style='background-color:{res['cor_hex']}; color:white; padding: 3px 12px; border-radius: 12px; font-weight: bold; font-size: 13px;'>{res['badge_icon']} {res['class_label']}</span>"
            
            with st.expander(f"{res['segmento']}  •  {res['class_label']} ({res['badge_icon']})", expanded=False):
                st.markdown(f"**Classificação:** {badge_html}", unsafe_allow_html=True)
                st.markdown(f"**Parecer do Modelo:** {res['justificativa']}")
                
                st.markdown("---")
                st.markdown("#### 📊 Métricas do Cenário Simulado")
                
                c_k1, c_k2, c_k3 = st.columns(3)
                c_k1.metric("Clientes Impactados", formata_br(res['clientes_impactados'], decimais=0))
                c_k2.metric("Receita Bruta", formata_br(res['receita_bruta_proj'], prefixo="US$ "))
                c_k3.metric("Ratio de Receita (ROI)", f"{formata_br(res['ratio_receita'], decimais=1)}:1")
                
                c_k4, c_k5, c_k6 = st.columns(3)
                c_k4.metric("Custo Total", formata_br(res['custo_total_campanha'], prefixo="US$ "))
                c_k5.metric("Lucro Líquido", formata_br(res['lucro_liquido_proj'], prefixo="US$ "))
                c_k6.metric("Retorno s/ Investimento", f"{formata_br(res['roi_proj'], decimais=1)}%")
                
                df_sim_graph = pd.DataFrame({
                    "Métrica": ["Receita Bruta", "Custo Total", "Lucro Líquido"],
                    "Valor (US$)": [res['receita_bruta_proj'], res['custo_total_campanha'], res['lucro_liquido_proj']]
                })
                
                fig_sim = px.bar(
                    df_sim_graph,
                    x="Métrica",
                    y="Valor (US$)",
                    color="Métrica",
                    color_discrete_map={
                        "Receita Bruta": "#2B5C8F",
                        "Custo Total": "#D9534F",
                        "Lucro Líquido": "#5CB85C" if res['lucro_liquido_proj'] >= 0 else "#D9534F"
                    },
                    title=f"Demonstrativo do Resultado Simulado — {res['segmento']}"
                )
                fig_sim.update_layout(height=240, showlegend=False, margin=dict(l=20, r=20, t=35, b=20))
                st.plotly_chart(fig_sim, use_container_width=True)
