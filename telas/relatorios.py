import io
import streamlit as st
import pandas as pd
import numpy as np
import openpyxl
import xlsxwriter

# IMPORTA AS MESMAS FUNÇÕES E CATEGORIAS DO SIMULADOR.PY
from .simulador import carregar_dados_rfm, aplicar_kmeans, ORDEM_ALFABETICA_CLUSTERS


def formata_br(valor, prefixo="", sufixo="", decimais=2):
    """Formata números no padrão brasileiro (milhar com ponto, decimal com vírgula)."""
    if valor is None or pd.isna(valor):
        return "N/A"
    try:
        fmt = f"{valor:,.{decimais}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{prefixo}{fmt}{sufixo}"
    except Exception:
        return str(valor)


def gerar_excel_com_observacao(df_dados, parametros_dict):
    """
    Gera um arquivo .xlsx em memória contendo a tabela consolidada (baseline + simulação)
    e adiciona a linha de observação dos parâmetros na primeira linha (célula A1).
    """
    buffer = io.BytesIO()

    texto_params = "Parâmetros utilizados na simulação: " + "; ".join(
        [f"{k} = {v}" for k, v in parametros_dict.items()]
    )

    df_export = df_dados.copy()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_export.to_excel(
            writer, sheet_name="Simulacao_Clusters", index=False, startrow=2
        )
        worksheet = writer.sheets["Simulacao_Clusters"]
        worksheet.cell(row=1, column=1, value=texto_params)

    buffer.seek(0)
    return buffer


def gerar_excel(df_dados, texto_filtros, nome_aba="Dados"):
    """
    Função genérica para exportar qualquer DataFrame para Excel com:
    - Resumo dos filtros na célula A1
    - Tabela de dados a partir da célula A3 (startrow=2)
    - Formatação automática de todas as colunas de data no padrão DD/MM/YYYY
    """
    buffer = io.BytesIO()
    df_export = df_dados.copy()

    for col in df_export.columns:
        if pd.api.types.is_datetime64_any_dtype(df_export[col]):
            df_export[col] = df_export[col].dt.strftime("%d/%m/%Y")

    try:
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df_export.to_excel(writer, sheet_name=nome_aba, index=False, startrow=2)
            ws = writer.sheets[nome_aba]
            ws["A1"] = texto_filtros
    except Exception:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            df_export.to_excel(writer, sheet_name=nome_aba, index=False, startrow=2)
            ws = writer.sheets[nome_aba]
            ws.write(0, 0, texto_filtros)

    buffer.seek(0)
    return buffer


def gerar_excel_relatorio_completo(
    df_clusters_excel, texto_params,
    df_eventos_filtrado, texto_eventos_a1,
    df_pedidos_filtrado, texto_pedidos_a1,
    df_clientes_filtrado, texto_clientes_a1,
):
    """
    Gera um único arquivo .xlsx com 4 abas, preservando os DataFrames filtrados
    em tela e registrando os filtros aplicados na célula A1 de cada aba.
    """
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        # Aba 1: Clusters e Simulação
        if df_clusters_excel is not None and not df_clusters_excel.empty:
            df_clusters_excel.to_excel(
                writer, sheet_name="Simulacao_Clusters", index=False, startrow=2
            )
            ws1 = writer.sheets["Simulacao_Clusters"]
            ws1.cell(row=1, column=1, value=texto_params)

        # Aba 2: Tráfego (Eventos)
        if df_eventos_filtrado is not None and not df_eventos_filtrado.empty:
            df_eventos_filtrado.to_excel(
                writer, sheet_name="Trafego", index=False, startrow=2
            )
            ws2 = writer.sheets["Trafego"]
            ws2.cell(row=1, column=1, value=texto_eventos_a1)

        # Aba 3: Vendas
        if df_pedidos_filtrado is not None and not df_pedidos_filtrado.empty:
            df_pedidos_filtrado.to_excel(
                writer, sheet_name="Vendas", index=False, startrow=2
            )
            ws3 = writer.sheets["Vendas"]
            ws3.cell(row=1, column=1, value=texto_pedidos_a1)

        # Aba 4: Clientes
        if df_clientes_filtrado is not None and not df_clientes_filtrado.empty:
            df_clientes_filtrado.to_excel(
                writer, sheet_name="Clientes", index=False, startrow=2
            )
            ws4 = writer.sheets["Clientes"]
            ws4.cell(row=1, column=1, value=texto_clientes_a1)

    buffer.seek(0)
    return buffer


@st.cache_data(show_spinner="Carregando dados de tráfego...")
def buscar_dados_eventos(_con, data_inicio, data_fim):
    query = f"""
        WITH mapa_localizacao AS (
            SELECT DISTINCT city, state, country
            FROM users
            WHERE country IS NOT NULL 
              AND LOWER(country) != 'não informado'
        )
        SELECT 
            TRY_CAST(e.created_at AS DATE) AS "Data do Evento",
            CASE e.event_type
                WHEN 'home' THEN 'Página Inicial'
                WHEN 'department' THEN 'Departamento'
                WHEN 'product' THEN 'Produto'
                WHEN 'cart' THEN 'Carrinho'
                WHEN 'purchase' THEN 'Compra'
                WHEN 'cancel' THEN 'Cancelamento'
                ELSE e.event_type
            END AS "Etapa",
            e.traffic_source AS "Origem do Tráfego",
            COALESCE(
                (SELECT ANY_VALUE(m.country) FROM mapa_localizacao m WHERE m.state = e.state AND m.city = e.city),
                (SELECT ANY_VALUE(m.country) FROM mapa_localizacao m WHERE m.state = e.state),
                (SELECT ANY_VALUE(m.country) FROM mapa_localizacao m WHERE m.city = e.city),
                'Não Informado'
            ) AS "País",
            COALESCE(e.state, 'Não Informado') AS "Estado",
            COALESCE(e.city, 'Não Informado') AS "Cidade",
            COUNT(DISTINCT e.session_id) AS "Sessões",
            COUNT(DISTINCT e.user_id) AS "Usuários"
        FROM events e
        WHERE TRY_CAST(e.created_at AS DATE) BETWEEN '{data_inicio}' AND '{data_fim}'
        GROUP BY ALL
        ORDER BY 1 DESC
    """
    return _con.execute(query).df()


@st.cache_data(show_spinner="Carregando dados de pedidos...")
def buscar_dados_pedidos(_con, data_inicio, data_fim):
    query = f"""
        SELECT 
            TRY_CAST(oi.created_at AS DATE) AS "Data do Pedido",
            COALESCE(u.country, 'Não Informado') AS "País do Usuário",
            COALESCE(u.state, 'Não Informado') AS "Estado do Usuário",
            COALESCE(u.city, 'Não Informado') AS "Cidade do Usuário",
            p.category AS "Categoria",
            p.department AS "Departamento",
            p.brand AS "Marca",
            p.name AS "Produto",
            dc.name AS "Centro de Distribuição",
            oi.status AS "Status",
            COUNT(oi.id) AS "Quantidade Vendida",
            ROUND(SUM(oi.sale_price), 2) AS "Receita Total (US$)",
            ROUND(SUM(p.cost), 2) AS "Custo Total (US$)",
            ROUND(SUM(oi.sale_price - p.cost), 2) AS "Margem de Lucro Bruto (US$)"
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        JOIN users u ON oi.user_id = u.id
        JOIN distribution_centers dc ON p.distribution_center_id = dc.id
        WHERE TRY_CAST(oi.created_at AS DATE) BETWEEN '{data_inicio}' AND '{data_fim}'
        GROUP BY ALL
        ORDER BY "Data do Pedido" DESC
    """
    return _con.execute(query).df()


@st.cache_data(show_spinner="Carregando dados de clientes...")
def buscar_dados_clientes(_con, data_inicio, data_fim):
    query = f"""
        SELECT 
            TRY_CAST(u.created_at AS DATE) AS "Data de Cadastro",
            COALESCE(u.country, 'Não Informado') AS "País",
            COALESCE(u.state, 'Não Informado') AS "Estado",
            COALESCE(u.city, 'Não Informado') AS "Cidade",
            COALESCE(u.gender, 'Não Informado') AS "Gênero",
            CASE 
                WHEN u.age < 18 THEN 'Menor que 18'
                WHEN u.age BETWEEN 18 AND 25 THEN '18-25 anos'
                WHEN u.age BETWEEN 26 AND 35 THEN '26-35 anos'
                WHEN u.age BETWEEN 36 AND 50 THEN '36-50 anos'
                WHEN u.age BETWEEN 51 AND 65 THEN '51-65 anos'
                ELSE '65+ anos'
            END AS "Faixa Etária",
            COALESCE(u.traffic_source, 'Não Informado') AS "Canal de Aquisição",
            COUNT(DISTINCT u.id) AS "Quantidade de Usuários",
            COUNT(DISTINCT o.order_id) AS "Quantidade de Pedidos",
            ROUND(COALESCE(SUM(oi.sale_price), 0), 2) AS "Faturamento Gerado (US$)",
            ROUND(COALESCE(SUM(p.cost), 0), 2) AS "Custo Total do Cliente (US$)",
            ROUND(COALESCE(SUM(oi.sale_price - p.cost), 0), 2) AS "LTV / Lucro Gerado (US$)"
        FROM users u
        LEFT JOIN orders o ON u.id = o.user_id
        LEFT JOIN order_items oi ON o.order_id = oi.order_id
        LEFT JOIN products p ON oi.product_id = p.id
        WHERE TRY_CAST(u.created_at AS DATE) BETWEEN '{data_inicio}' AND '{data_fim}'
        GROUP BY ALL
        ORDER BY "Data de Cadastro" DESC
    """
    return _con.execute(query).df()


def renderizar(con):
    st.title("📊 Relatórios Analíticos")
    st.caption(
        "Consolidação estratégica de segmentação, simulações, tráfego web, vendas e perfil de clientes."
    )

    # 1. Inicializa variáveis de relatório com valores padrão no escopo da função
    texto_params = "Parâmetros utilizados na simulação: Padrão"
    texto_eventos_a1 = "Filtros aplicados: Período completo"
    texto_pedidos_a1 = "Filtros aplicados: Período completo"
    texto_clientes_a1 = "Filtros aplicados: Período completo"

    df_consolidado_excel = pd.DataFrame()
    df_eventos_filtrado = pd.DataFrame()
    df_pedidos_filtrado = pd.DataFrame()
    df_clientes_filtrado = pd.DataFrame()

    # ==============================================================================
    # PARTE 1: SEGMENTAÇÃO DE CLIENTES & PARECER DA ÚLTIMA SIMULAÇÃO
    # ==============================================================================
    st.markdown("---")
    st.subheader("🎯 Parecer da Simulação e Diagnóstico dos Clusters")

    # Recupera parâmetros salvos do simulador (prioriza chaves persistentes val_*)
    tx_base = st.session_state.get(
        "val_tx_conversao", st.session_state.get("sim_tx_conversao", 12.0)
    )
    desc_prom = st.session_state.get(
        "val_pct_desconto", st.session_state.get("sim_pct_desconto", 10.0)
    )
    custo_fx = st.session_state.get(
        "val_custo_fixo", st.session_state.get("sim_custo_fixo", 1000.0)
    )
    romi_meta = st.session_state.get(
        "val_meta_romi", st.session_state.get("sim_meta_romi", 4.0)
    )

    # Dicionário formatado com a função formata_br
    dict_params = {
        "Taxa Média de Resposta Base (%)": formata_br(tx_base, sufixo="%", decimais=1),
        "Desconto Promocional (%)": formata_br(desc_prom, sufixo="%", decimais=1),
        "Custo Fixo por Segmento (US$)": formata_br(custo_fx, prefixo="US$ ", decimais=2),
        "Meta de ROMI (x:1)": formata_br(romi_meta, sufixo=":1", decimais=1),
    }

    # ATUALIZA texto_params PARA O RELATÓRIO CONSOLIDADO
    texto_params = "Parâmetros utilizados na simulação: " + "; ".join(
        [f"{k} = {v}" for k, v in dict_params.items()]
    )

    st.markdown("##### ⚙️ Parâmetros Utilizados na Última Simulação")
    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    col_p1.metric("Taxa Resposta Base", dict_params["Taxa Média de Resposta Base (%)"])
    col_p2.metric("Desconto Promocional", dict_params["Desconto Promocional (%)"])
    col_p3.metric("Custo Fixo / Segmento", dict_params["Custo Fixo por Segmento (US$)"])
    col_p4.metric("Meta de ROMI", dict_params["Meta de ROMI (x:1)"])

    # CHAMA A MESMA CLUSTERIZAÇÃO K-MEANS DO SIMULADOR.PY
    df_rfm = carregar_dados_rfm(con)

    if not df_rfm.empty:
        df_clustered = aplicar_kmeans(df_rfm, n_clusters=4)

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

        # Tabela 1A: Baseline K-Means
        st.markdown("##### 📋 Dados Atuais dos Segmentos")
        df_1a_display = pd.DataFrame(
            {
                "Segmento (Cluster)": resumo_clusters["cluster_nome"],
                "Total de Clientes": resumo_clusters["Total_Clientes"],
                "Recência Média (Dias)": resumo_clusters["Recencia_Media"].round(1),
                "Frequência Média (Pedidos)": resumo_clusters["Frequencia_Media"].round(2),
                "Ticket Médio (US$)": resumo_clusters["Ticket_Medio"].round(2),
                "Receita Total (US$)": resumo_clusters["Valor_Total"].round(2),
                "Lucro Total (US$)": resumo_clusters["Lucro_Total"].round(2),
            }
        )

        st.dataframe(
            df_1a_display,
            column_config={
                "Segmento (Cluster)": st.column_config.TextColumn("Segmento (Cluster)"),
                "Total de Clientes": st.column_config.NumberColumn("Total de Clientes", format="%d"),
                "Recência Média (Dias)": st.column_config.NumberColumn("Recência Média (Dias)", format="%.1f"),
                "Frequência Média (Pedidos)": st.column_config.NumberColumn("Frequência Média (Pedidos)", format="%.2f"),
                "Ticket Médio (US$)": st.column_config.NumberColumn("Ticket Médio (US$)", format="$ %.2f"),
                "Receita Total (US$)": st.column_config.NumberColumn("Receita Total (US$)", format="$ %.2f"),
                "Lucro Total (US$)": st.column_config.NumberColumn("Lucro Total (US$)", format="$ %.2f"),
            },
            use_container_width=True,
            hide_index=True,
        )

        # Tabela 1B: Resultado Simulado por Cluster
        st.markdown("##### 🚀 Resultado Simulado por Segmento")
        recencia_global = df_clustered["recencia"].mean()

        dados_simulados_display = []
        dados_consolidados_excel = []

        for _, row_cluster in resumo_clusters.iterrows():
            seg = str(row_cluster["cluster_nome"])
            df_target = df_clustered[df_clustered["cluster_nome"] == seg]
            n_clientes = len(df_target)
            ticket_medio = row_cluster["Ticket_Medio"]
            custo_prod = df_target["custo_medio_produto"].mean()
            recencia_seg = row_cluster["Recencia_Media"]

            fator_recencia = np.exp(-0.5 * (recencia_seg / recencia_global))
            fator_promocional = 1.0 + (desc_prom / 100.0) * 1.2
            taxa_conversao_efetiva = min(tx_base * fator_recencia * fator_promocional, 50.0)
            clientes_impactados = int(n_clientes * (taxa_conversao_efetiva / 100.0))

            receita_bruta = clientes_impactados * ticket_medio
            custo_desconto = receita_bruta * (desc_prom / 100.0)
            custo_total = custo_desconto + custo_fx
            lucro_bruto = clientes_impactados * (ticket_medio - custo_prod)
            lucro_liquido = lucro_bruto - custo_total
            ratio_receita = (receita_bruta / custo_total) if custo_total > 0 else 0.0

            if lucro_liquido > 0 and ratio_receita >= romi_meta:
                diag = "Bom"
            elif lucro_liquido > 0:
                diag = "Médio"
            else:
                diag = "Ruim"

            dados_simulados_display.append(
                {
                    "Segmento (Cluster)": seg,
                    "Taxa Resposta Efetiva (%)": round(taxa_conversao_efetiva, 1),
                    "Clientes Convertidos": clientes_impactados,
                    "Receita Projetada (US$)": round(receita_bruta, 2),
                    "Custo Total (US$)": round(custo_total, 2),
                    "Lucro Líquido Proj. (US$)": round(lucro_liquido, 2),
                    "ROMI (x:1)": round(ratio_receita, 2),
                    "Diagnóstico": diag,
                }
            )

            dados_consolidados_excel.append(
                {
                    "Segmento (Cluster)": seg,
                    "Total de Clientes (Atual)": int(n_clientes),
                    "Recência Média (Dias)": round(float(recencia_seg), 1),
                    "Frequência Média (Pedidos)": round(float(row_cluster["Frequencia_Media"]), 2),
                    "Ticket Médio (US$)": round(float(ticket_medio), 2),
                    "Receita Histórica Total (US$)": round(float(row_cluster["Valor_Total"]), 2),
                    "Lucro Histórico Total (US$)": round(float(row_cluster["Lucro_Total"]), 2),
                    "Taxa Resposta Efetiva (%)": round(float(taxa_conversao_efetiva), 1),
                    "Clientes Convertidos (Simulado)": int(clientes_impactados),
                    "Receita Projetada (US$)": round(float(receita_bruta), 2),
                    "Custo Total Simulado (US$)": round(float(custo_total), 2),
                    "Lucro Líquido Proj. (US$)": round(float(lucro_liquido), 2),
                    "ROMI (x:1)": round(float(ratio_receita), 2),
                    "Diagnóstico": diag,
                }
            )

        df_simulacao_resultado = pd.DataFrame(dados_simulados_display)
        st.dataframe(
            df_simulacao_resultado,
            column_config={
                "Segmento (Cluster)": st.column_config.TextColumn("Segmento (Cluster)"),
                "Taxa Resposta Efetiva (%)": st.column_config.NumberColumn("Taxa Resposta Efetiva (%)", format="%.1f %%"),
                "Clientes Convertidos": st.column_config.NumberColumn("Clientes Convertidos", format="%d"),
                "Receita Projetada (US$)": st.column_config.NumberColumn("Receita Projetada (US$)", format="$ %.2f"),
                "Custo Total (US$)": st.column_config.NumberColumn("Custo Total (US$)", format="$ %.2f"),
                "Lucro Líquido Proj. (US$)": st.column_config.NumberColumn("Lucro Líquido Proj. (US$)", format="$ %.2f"),
                "ROMI (x:1)": st.column_config.NumberColumn("ROMI (x:1)", format="%.2f"),
                "Diagnóstico": st.column_config.TextColumn("Diagnóstico"),
            },
            use_container_width=True,
            hide_index=True,
        )

        df_consolidado_excel = pd.DataFrame(dados_consolidados_excel)
        excel_bytes = gerar_excel_com_observacao(df_consolidado_excel, dict_params)
        st.download_button(
            label="📥 Exportar em Excel (.xlsx)",
            data=excel_bytes,
            file_name="simulacao_clusters.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # ==============================================================================
    # PARTE 2: ANALÍTICO GERAL DE TRÁFEGO WEB (EVENTOS)
    # ==============================================================================
    st.markdown("---")
    st.subheader("🌐 Analítico Geral de Tráfego Web e Eventos")
    st.caption(
        "Mapeamento de acessos, navegação e conversão do funil por localização geográfica e origem do tráfego."
    )

    col_e1, col_e2, col_e3 = st.columns(3)
    with col_e1:
        data_inicio_e = st.date_input("Data Inicial", pd.to_datetime("2023-01-01"), format="DD/MM/YYYY", key="data_inicio_e")
    with col_e2:
        data_fim_e = st.date_input("Data Final", pd.to_datetime("2024-12-31"), format="DD/MM/YYYY", key="data_fim_e")

    try:
        df_eventos = buscar_dados_eventos(con, data_inicio_e, data_fim_e)
    except Exception:
        df_eventos = pd.DataFrame()

    if not df_eventos.empty:
        df_eventos["Data do Evento"] = pd.to_datetime(df_eventos["Data do Evento"])
        colunas_ordem = ["Data do Evento", "País", "Estado", "Cidade", "Etapa", "Origem do Tráfego", "Sessões", "Usuários"]
        df_eventos = df_eventos[[c for c in colunas_ordem if c in df_eventos.columns]]

        chaves_eventos = ["saved_filter_evt_pais", "saved_filter_evt_est", "saved_filter_evt_cid", "saved_filter_evt_etapa", "saved_filter_evt_origem"]
        for k in chaves_eventos:
            if k not in st.session_state:
                st.session_state[k] = []

        sel_pais_evt_atual = st.session_state["saved_filter_evt_pais"]
        sel_est_evt_atual = st.session_state["saved_filter_evt_est"]
        sel_cid_evt_atual = st.session_state["saved_filter_evt_cid"]
        sel_etapa_evt_atual = st.session_state["saved_filter_evt_etapa"]
        sel_origem_evt_atual = st.session_state["saved_filter_evt_origem"]

        def filtrar_base_evt(exceto=None):
            df_temp = df_eventos.copy()
            if exceto != "pais" and sel_pais_evt_atual:
                df_temp = df_temp[df_temp["País"].isin(sel_pais_evt_atual)]
            if exceto != "est" and sel_est_evt_atual:
                df_temp = df_temp[df_temp["Estado"].isin(sel_est_evt_atual)]
            if exceto != "cid" and sel_cid_evt_atual:
                df_temp = df_temp[df_temp["Cidade"].isin(sel_cid_evt_atual)]
            if exceto != "etapa" and sel_etapa_evt_atual:
                df_temp = df_temp[df_temp["Etapa"].isin(sel_etapa_evt_atual)]
            if exceto != "origem" and sel_origem_evt_atual:
                df_temp = df_temp[df_temp["Origem do Tráfego"].isin(sel_origem_evt_atual)]
            return df_temp

        opcoes_pais_evt = sorted(filtrar_base_evt("pais")["País"].dropna().unique().tolist())
        opcoes_est_evt = sorted(filtrar_base_evt("est")["Estado"].dropna().unique().tolist())
        opcoes_cid_evt = sorted(filtrar_base_evt("cid")["Cidade"].dropna().unique().tolist())
        opcoes_etapa_evt = sorted(filtrar_base_evt("etapa")["Etapa"].dropna().unique().tolist())
        opcoes_origem_evt = sorted(filtrar_base_evt("origem")["Origem do Tráfego"].dropna().unique().tolist())

        st.session_state["saved_filter_evt_pais"] = [x for x in st.session_state["saved_filter_evt_pais"] if x in opcoes_pais_evt]
        st.session_state["saved_filter_evt_est"] = [x for x in st.session_state["saved_filter_evt_est"] if x in opcoes_est_evt]
        st.session_state["saved_filter_evt_cid"] = [x for x in st.session_state["saved_filter_evt_cid"] if x in opcoes_cid_evt]
        st.session_state["saved_filter_evt_etapa"] = [x for x in st.session_state["saved_filter_evt_etapa"] if x in opcoes_etapa_evt]
        st.session_state["saved_filter_evt_origem"] = [x for x in st.session_state["saved_filter_evt_origem"] if x in opcoes_origem_evt]

        st.session_state["widget_filter_evt_pais"] = st.session_state["saved_filter_evt_pais"]
        st.session_state["widget_filter_evt_est"] = st.session_state["saved_filter_evt_est"]
        st.session_state["widget_filter_evt_cid"] = st.session_state["saved_filter_evt_cid"]
        st.session_state["widget_filter_evt_etapa"] = st.session_state["saved_filter_evt_etapa"]
        st.session_state["widget_filter_evt_origem"] = st.session_state["saved_filter_evt_origem"]

        with col_e3:
            st.write("")
            st.write("")
            with st.popover("⚙️ Filtrar por Colunas"):
                sel_pais_evt = st.multiselect("País:", options=opcoes_pais_evt, key="widget_filter_evt_pais", on_change=lambda: st.session_state.update({"saved_filter_evt_pais": st.session_state["widget_filter_evt_pais"]}))
                sel_est_evt = st.multiselect("Estado:", options=opcoes_est_evt, key="widget_filter_evt_est", on_change=lambda: st.session_state.update({"saved_filter_evt_est": st.session_state["widget_filter_evt_est"]}))
                sel_cid_evt = st.multiselect("Cidade:", options=opcoes_cid_evt, key="widget_filter_evt_cid", on_change=lambda: st.session_state.update({"saved_filter_evt_cid": st.session_state["widget_filter_evt_cid"]}))
                sel_etapa_evt = st.multiselect("Etapa:", options=opcoes_etapa_evt, key="widget_filter_evt_etapa", on_change=lambda: st.session_state.update({"saved_filter_evt_etapa": st.session_state["widget_filter_evt_etapa"]}))
                sel_origem_evt = st.multiselect("Origem do Tráfego:", options=opcoes_origem_evt, key="widget_filter_evt_origem", on_change=lambda: st.session_state.update({"saved_filter_evt_origem": st.session_state["widget_filter_evt_origem"]}))

                st.markdown("---")
                if st.button("🔄 Resetar Filtros (Tráfego)", use_container_width=True):
                    for k in chaves_eventos:
                        st.session_state[k] = []
                        w_key = k.replace("saved_", "widget_")
                        if w_key in st.session_state:
                            del st.session_state[w_key]
                    st.rerun()

        df_eventos_filtrado = df_eventos.copy()
        if sel_pais_evt:
            df_eventos_filtrado = df_eventos_filtrado[df_eventos_filtrado["País"].isin(sel_pais_evt)]
        if sel_est_evt:
            df_eventos_filtrado = df_eventos_filtrado[df_eventos_filtrado["Estado"].isin(sel_est_evt)]
        if sel_cid_evt:
            df_eventos_filtrado = df_eventos_filtrado[df_eventos_filtrado["Cidade"].isin(sel_cid_evt)]
        if sel_etapa_evt:
            df_eventos_filtrado = df_eventos_filtrado[df_eventos_filtrado["Etapa"].isin(sel_etapa_evt)]
        if sel_origem_evt:
            df_eventos_filtrado = df_eventos_filtrado[df_eventos_filtrado["Origem do Tráfego"].isin(sel_origem_evt)]

        st.dataframe(
            df_eventos_filtrado,
            column_config={
                "Data do Evento": st.column_config.DateColumn("Data do Evento", format="DD/MM/YYYY"),
                "Sessões": st.column_config.NumberColumn("Sessões", format="%d"),
                "Usuários": st.column_config.NumberColumn("Usuários", format="%d"),
            },
            use_container_width=True,
            hide_index=True,
        )

        detalhes_filtros_e = [f"Período: {data_inicio_e.strftime('%d/%m/%Y')} a {data_fim_e.strftime('%d/%m/%Y')}"]
        if sel_pais_evt:
            detalhes_filtros_e.append(f"País: {', '.join(sel_pais_evt)}")
        if sel_est_evt:
            detalhes_filtros_e.append(f"Estado: {', '.join(sel_est_evt)}")
        if sel_cid_evt:
            detalhes_filtros_e.append(f"Cidade: {', '.join(sel_cid_evt)}")
        if sel_etapa_evt:
            detalhes_filtros_e.append(f"Etapa: {', '.join(sel_etapa_evt)}")
        if sel_origem_evt:
            detalhes_filtros_e.append(f"Origem: {', '.join(sel_origem_evt)}")

        texto_eventos_a1 = "Filtros aplicados: " + " | ".join(detalhes_filtros_e)

        st.download_button(
            label="📥 Exportar Analítico de Tráfego em Excel (.xlsx)",
            data=lambda: gerar_excel(df_eventos_filtrado, texto_eventos_a1, nome_aba="Trafego_Web"),
            file_name="trafego.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.warning("Nenhum evento de tráfego encontrado para o período selecionado.")

    # ==============================================================================
    # PARTE 3: ANALÍTICO DE PEDIDOS E COMPRAS DE PRODUTOS
    # ==============================================================================
    st.markdown("---")
    st.subheader("🛍️ Analítico Completo de Pedidos e Vendas de Produtos")
    st.caption(
        "Detalhamento comercial, logístico e geográfico das vendas agrupado por item, categoria e localização do usuário."
    )

    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        data_inicio_p = st.date_input("Data Inicial", pd.to_datetime("2023-01-01"), format="DD/MM/YYYY", key="data_inicio_p")
    with col_p2:
        data_fim_p = st.date_input("Data Final", pd.to_datetime("2024-12-31"), format="DD/MM/YYYY", key="data_fim_p")

    try:
        df_pedidos = buscar_dados_pedidos(con, data_inicio_p, data_fim_p)
    except Exception:
        df_pedidos = pd.DataFrame()

    if not df_pedidos.empty:
        df_pedidos["Data do Pedido"] = pd.to_datetime(df_pedidos["Data do Pedido"])

        chaves_pedidos = ["saved_filter_ped_pais", "saved_filter_ped_estado", "saved_filter_ped_cidade", "saved_filter_ped_cat", "saved_filter_ped_dep", "saved_filter_ped_status", "saved_filter_ped_marca", "saved_filter_ped_centro"]
        for k in chaves_pedidos:
            if k not in st.session_state:
                st.session_state[k] = []

        sel_pais_atual = st.session_state["saved_filter_ped_pais"]
        sel_est_atual = st.session_state["saved_filter_ped_estado"]
        sel_cid_atual = st.session_state["saved_filter_ped_cidade"]
        sel_cat_atual = st.session_state["saved_filter_ped_cat"]
        sel_dep_atual = st.session_state["saved_filter_ped_dep"]
        sel_status_atual = st.session_state["saved_filter_ped_status"]
        sel_marca_atual = st.session_state["saved_filter_ped_marca"]
        sel_centro_atual = st.session_state["saved_filter_ped_centro"]

        def filtrar_base_ped(exceto=None):
            df_temp = df_pedidos.copy()
            if exceto != "pais" and sel_pais_atual:
                df_temp = df_temp[df_temp["País do Usuário"].isin(sel_pais_atual)]
            if exceto != "estado" and sel_est_atual:
                df_temp = df_temp[df_temp["Estado do Usuário"].isin(sel_est_atual)]
            if exceto != "cidade" and sel_cid_atual:
                df_temp = df_temp[df_temp["Cidade do Usuário"].isin(sel_cid_atual)]
            if exceto != "cat" and sel_cat_atual:
                df_temp = df_temp[df_temp["Categoria"].isin(sel_cat_atual)]
            if exceto != "dep" and sel_dep_atual:
                df_temp = df_temp[df_temp["Departamento"].isin(sel_dep_atual)]
            if exceto != "status" and sel_status_atual:
                df_temp = df_temp[df_temp["Status"].isin(sel_status_atual)]
            if exceto != "marca" and sel_marca_atual:
                df_temp = df_temp[df_temp["Marca"].isin(sel_marca_atual)]
            if exceto != "centro" and sel_centro_atual:
                df_temp = df_temp[df_temp["Centro de Distribuição"].isin(sel_centro_atual)]
            return df_temp

        opcoes_pais = sorted(filtrar_base_ped("pais")["País do Usuário"].dropna().unique().tolist())
        opcoes_estado = sorted(filtrar_base_ped("estado")["Estado do Usuário"].dropna().unique().tolist())
        opcoes_cidade = sorted(filtrar_base_ped("cidade")["Cidade do Usuário"].dropna().unique().tolist())
        opcoes_cat = sorted(filtrar_base_ped("cat")["Categoria"].dropna().unique().tolist())
        opcoes_dep = sorted(filtrar_base_ped("dep")["Departamento"].dropna().unique().tolist())
        opcoes_status = sorted(filtrar_base_ped("status")["Status"].dropna().unique().tolist())
        opcoes_marca = sorted(filtrar_base_ped("marca")["Marca"].dropna().unique().tolist())
        opcoes_centro = sorted(filtrar_base_ped("centro")["Centro de Distribuição"].dropna().unique().tolist())

        st.session_state["saved_filter_ped_pais"] = [x for x in st.session_state["saved_filter_ped_pais"] if x in opcoes_pais]
        st.session_state["saved_filter_ped_estado"] = [x for x in st.session_state["saved_filter_ped_estado"] if x in opcoes_estado]
        st.session_state["saved_filter_ped_cidade"] = [x for x in st.session_state["saved_filter_ped_cidade"] if x in opcoes_cidade]
        st.session_state["saved_filter_ped_cat"] = [x for x in st.session_state["saved_filter_ped_cat"] if x in opcoes_cat]
        st.session_state["saved_filter_ped_dep"] = [x for x in st.session_state["saved_filter_ped_dep"] if x in opcoes_dep]
        st.session_state["saved_filter_ped_status"] = [x for x in st.session_state["saved_filter_ped_status"] if x in opcoes_status]
        st.session_state["saved_filter_ped_marca"] = [x for x in st.session_state["saved_filter_ped_marca"] if x in opcoes_marca]
        st.session_state["saved_filter_ped_centro"] = [x for x in st.session_state["saved_filter_ped_centro"] if x in opcoes_centro]

        st.session_state["widget_filter_ped_pais"] = st.session_state["saved_filter_ped_pais"]
        st.session_state["widget_filter_ped_estado"] = st.session_state["saved_filter_ped_estado"]
        st.session_state["widget_filter_ped_cidade"] = st.session_state["saved_filter_ped_cidade"]
        st.session_state["widget_filter_ped_cat"] = st.session_state["saved_filter_ped_cat"]
        st.session_state["widget_filter_ped_dep"] = st.session_state["saved_filter_ped_dep"]
        st.session_state["widget_filter_ped_status"] = st.session_state["saved_filter_ped_status"]
        st.session_state["widget_filter_ped_marca"] = st.session_state["saved_filter_ped_marca"]
        st.session_state["widget_filter_ped_centro"] = st.session_state["saved_filter_ped_centro"]

        with col_p3:
            st.write("")
            st.write("")
            with st.popover("⚙️ Filtrar por Colunas"):
                sel_pais = st.multiselect("País do Usuário:", options=opcoes_pais, key="widget_filter_ped_pais", on_change=lambda: st.session_state.update({"saved_filter_ped_pais": st.session_state["widget_filter_ped_pais"]}))
                sel_estado = st.multiselect("Estado do Usuário:", options=opcoes_estado, key="widget_filter_ped_estado", on_change=lambda: st.session_state.update({"saved_filter_ped_estado": st.session_state["widget_filter_ped_estado"]}))
                sel_cidade = st.multiselect("Cidade do Usuário:", options=opcoes_cidade, key="widget_filter_ped_cidade", on_change=lambda: st.session_state.update({"saved_filter_ped_cidade": st.session_state["widget_filter_ped_cidade"]}))
                sel_cat = st.multiselect("Categoria:", options=opcoes_cat, key="widget_filter_ped_cat", on_change=lambda: st.session_state.update({"saved_filter_ped_cat": st.session_state["widget_filter_ped_cat"]}))
                sel_dep = st.multiselect("Departamento:", options=opcoes_dep, key="widget_filter_ped_dep", on_change=lambda: st.session_state.update({"saved_filter_ped_dep": st.session_state["widget_filter_ped_dep"]}))
                sel_marca = st.multiselect("Marca:", options=opcoes_marca, key="widget_filter_ped_marca", on_change=lambda: st.session_state.update({"saved_filter_ped_marca": st.session_state["widget_filter_ped_marca"]}))
                sel_centro = st.multiselect("Centro de Distribuição:", options=opcoes_centro, key="widget_filter_ped_centro", on_change=lambda: st.session_state.update({"saved_filter_ped_centro": st.session_state["widget_filter_ped_centro"]}))
                sel_status = st.multiselect("Status do Pedido:", options=opcoes_status, key="widget_filter_ped_status", on_change=lambda: st.session_state.update({"saved_filter_ped_status": st.session_state["widget_filter_ped_status"]}))

                if st.button("🔄 Resetar Filtros", use_container_width=True, key="resetar_filtros_p"):
                    for k in chaves_pedidos:
                        st.session_state[k] = []
                        w_key = k.replace("saved_", "widget_")
                        if w_key in st.session_state:
                            del st.session_state[w_key]
                    st.rerun()

        df_pedidos_filtrado = df_pedidos.copy()
        if sel_pais:
            df_pedidos_filtrado = df_pedidos_filtrado[df_pedidos_filtrado["País do Usuário"].isin(sel_pais)]
        if sel_estado:
            df_pedidos_filtrado = df_pedidos_filtrado[df_pedidos_filtrado["Estado do Usuário"].isin(sel_estado)]
        if sel_cidade:
            df_pedidos_filtrado = df_pedidos_filtrado[df_pedidos_filtrado["Cidade do Usuário"].isin(sel_cidade)]
        if sel_cat:
            df_pedidos_filtrado = df_pedidos_filtrado[df_pedidos_filtrado["Categoria"].isin(sel_cat)]
        if sel_dep:
            df_pedidos_filtrado = df_pedidos_filtrado[df_pedidos_filtrado["Departamento"].isin(sel_dep)]
        if sel_status:
            df_pedidos_filtrado = df_pedidos_filtrado[df_pedidos_filtrado["Status"].isin(sel_status)]
        if sel_marca:
            df_pedidos_filtrado = df_pedidos_filtrado[df_pedidos_filtrado["Marca"].isin(sel_marca)]
        if sel_centro:
            df_pedidos_filtrado = df_pedidos_filtrado[df_pedidos_filtrado["Centro de Distribuição"].isin(sel_centro)]

        st.dataframe(
            df_pedidos_filtrado,
            column_config={
                "Data do Pedido": st.column_config.DateColumn("Data do Pedido", format="DD/MM/YYYY"),
                "Quantidade Vendida": st.column_config.NumberColumn("Quantidade Vendida", format="%d"),
                "Receita Total (US$)": st.column_config.NumberColumn("Receita Total (US$)", format="$ %.2f"),
                "Custo Total (US$)": st.column_config.NumberColumn("Custo Total (US$)", format="$ %.2f"),
                "Margem de Lucro Bruto (US$)": st.column_config.NumberColumn("Margem de Lucro Bruto (US$)", format="$ %.2f"),
            },
            use_container_width=True,
            hide_index=True,
        )

        detalhes_filtros_p = [f"Período: {data_inicio_p.strftime('%d/%m/%Y')} a {data_fim_p.strftime('%d/%m/%Y')}"]
        if sel_pais:
            detalhes_filtros_p.append(f"País: {', '.join(sel_pais)}")
        if sel_estado:
            detalhes_filtros_p.append(f"Estado: {', '.join(sel_estado)}")
        if sel_cidade:
            detalhes_filtros_p.append(f"Cidade: {', '.join(sel_cidade)}")
        if sel_cat:
            detalhes_filtros_p.append(f"Categoria: {', '.join(sel_cat)}")
        if sel_dep:
            detalhes_filtros_p.append(f"Departamento: {', '.join(sel_dep)}")
        if sel_status:
            detalhes_filtros_p.append(f"Status: {', '.join(sel_status)}")
        if sel_marca:
            detalhes_filtros_p.append(f"Marca: {', '.join(sel_marca)}")
        if sel_centro:
            detalhes_filtros_p.append(f"Centro: {', '.join(sel_centro)}")

        texto_pedidos_a1 = "Filtros aplicados: " + " | ".join(detalhes_filtros_p)

        st.download_button(
            label="📥 Exportar em Excel (.xlsx)",
            data=lambda: gerar_excel(df_pedidos_filtrado, texto_pedidos_a1, nome_aba="Vendas"),
            file_name="vendas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.warning("Nenhum pedido encontrado para o período selecionado.")

    # ==============================================================================
    # PARTE 4: ANALÍTICO DE CLIENTES E CONSUMIDORES
    # ==============================================================================
    st.markdown("---")
    st.subheader("👥 Analítico Completo de Perfil e Comportamento dos Clientes")
    st.caption(
        "Detalhamento demográfico, geográfico e financeiro (LTV/Faturamento) agrupado pela data de cadastro dos usuários."
    )

    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1:
        data_inicio_c = st.date_input("Data Inicial", pd.to_datetime("2023-01-01"), format="DD/MM/YYYY", key="data_inicio_c")
    with col_c2:
        data_fim_c = st.date_input("Data Final", pd.to_datetime("2024-12-31"), format="DD/MM/YYYY", key="data_fim_c")

    try:
        df_clientes = buscar_dados_clientes(con, data_inicio_c, data_fim_c)
    except Exception:
        df_clientes = pd.DataFrame()

    if not df_clientes.empty:
        df_clientes["Data de Cadastro"] = pd.to_datetime(df_clientes["Data de Cadastro"])

        chaves_clientes = ["saved_filter_cli_pais", "saved_filter_cli_est", "saved_filter_cli_cid", "saved_filter_cli_gen", "saved_filter_cli_faixa", "saved_filter_cli_canal"]
        for k in chaves_clientes:
            if k not in st.session_state:
                st.session_state[k] = []

        sel_pais_cli_atual = st.session_state["saved_filter_cli_pais"]
        sel_est_cli_atual = st.session_state["saved_filter_cli_est"]
        sel_cid_cli_atual = st.session_state["saved_filter_cli_cid"]
        sel_gen_cli_atual = st.session_state["saved_filter_cli_gen"]
        sel_faixa_cli_atual = st.session_state["saved_filter_cli_faixa"]
        sel_canal_cli_atual = st.session_state["saved_filter_cli_canal"]

        def filtrar_base_cli(exceto=None):
            df_temp = df_clientes.copy()
            if exceto != "pais" and sel_pais_cli_atual:
                df_temp = df_temp[df_temp["País"].isin(sel_pais_cli_atual)]
            if exceto != "est" and sel_est_cli_atual:
                df_temp = df_temp[df_temp["Estado"].isin(sel_est_cli_atual)]
            if exceto != "cid" and sel_cid_cli_atual:
                df_temp = df_temp[df_temp["Cidade"].isin(sel_cid_cli_atual)]
            if exceto != "gen" and sel_gen_cli_atual:
                df_temp = df_temp[df_temp["Gênero"].isin(sel_gen_cli_atual)]
            if exceto != "faixa" and sel_faixa_cli_atual:
                df_temp = df_temp[df_temp["Faixa Etária"].isin(sel_faixa_cli_atual)]
            if exceto != "canal" and sel_canal_cli_atual:
                df_temp = df_temp[df_temp["Canal de Aquisição"].isin(sel_canal_cli_atual)]
            return df_temp

        opcoes_pais_cli = sorted(filtrar_base_cli("pais")["País"].dropna().unique().tolist())
        opcoes_est_cli = sorted(filtrar_base_cli("est")["Estado"].dropna().unique().tolist())
        opcoes_cid_cli = sorted(filtrar_base_cli("cid")["Cidade"].dropna().unique().tolist())
        opcoes_gen_cli = sorted(filtrar_base_cli("gen")["Gênero"].dropna().unique().tolist())
        opcoes_faixa_cli = sorted(filtrar_base_cli("faixa")["Faixa Etária"].dropna().unique().tolist())
        opcoes_canal_cli = sorted(filtrar_base_cli("canal")["Canal de Aquisição"].dropna().unique().tolist())

        st.session_state["saved_filter_cli_pais"] = [x for x in st.session_state["saved_filter_cli_pais"] if x in opcoes_pais_cli]
        st.session_state["saved_filter_cli_est"] = [x for x in st.session_state["saved_filter_cli_est"] if x in opcoes_est_cli]
        st.session_state["saved_filter_cli_cid"] = [x for x in st.session_state["saved_filter_cli_cid"] if x in opcoes_cid_cli]
        st.session_state["saved_filter_cli_gen"] = [x for x in st.session_state["saved_filter_cli_gen"] if x in opcoes_gen_cli]
        st.session_state["saved_filter_cli_faixa"] = [x for x in st.session_state["saved_filter_cli_faixa"] if x in opcoes_faixa_cli]
        st.session_state["saved_filter_cli_canal"] = [x for x in st.session_state["saved_filter_cli_canal"] if x in opcoes_canal_cli]

        st.session_state["widget_filter_cli_pais"] = st.session_state["saved_filter_cli_pais"]
        st.session_state["widget_filter_cli_est"] = st.session_state["saved_filter_cli_est"]
        st.session_state["widget_filter_cli_cid"] = st.session_state["saved_filter_cli_cid"]
        st.session_state["widget_filter_cli_gen"] = st.session_state["saved_filter_cli_gen"]
        st.session_state["widget_filter_cli_faixa"] = st.session_state["saved_filter_cli_faixa"]
        st.session_state["widget_filter_cli_canal"] = st.session_state["saved_filter_cli_canal"]

        with col_c3:
            st.write("")
            st.write("")
            with st.popover("⚙️ Filtrar por Colunas"):
                sel_pais_cli = st.multiselect("País:", options=opcoes_pais_cli, key="widget_filter_cli_pais", on_change=lambda: st.session_state.update({"saved_filter_cli_pais": st.session_state["widget_filter_cli_pais"]}))
                sel_est_cli = st.multiselect("Estado:", options=opcoes_est_cli, key="widget_filter_cli_est", on_change=lambda: st.session_state.update({"saved_filter_cli_est": st.session_state["widget_filter_cli_est"]}))
                sel_cid_cli = st.multiselect("Cidade:", options=opcoes_cid_cli, key="widget_filter_cli_cid", on_change=lambda: st.session_state.update({"saved_filter_cli_cid": st.session_state["widget_filter_cli_cid"]}))
                sel_gen_cli = st.multiselect("Gênero:", options=opcoes_gen_cli, key="widget_filter_cli_gen", on_change=lambda: st.session_state.update({"saved_filter_cli_gen": st.session_state["widget_filter_cli_gen"]}))
                sel_faixa_cli = st.multiselect("Faixa Etária:", options=opcoes_faixa_cli, key="widget_filter_cli_faixa", on_change=lambda: st.session_state.update({"saved_filter_cli_faixa": st.session_state["widget_filter_cli_faixa"]}))
                sel_canal_cli = st.multiselect("Canal de Aquisição:", options=opcoes_canal_cli, key="widget_filter_cli_canal", on_change=lambda: st.session_state.update({"saved_filter_cli_canal": st.session_state["widget_filter_cli_canal"]}))

                if st.button("🔄 Resetar Filtros", use_container_width=True, key="resetar_filtros_c"):
                    for k in chaves_clientes:
                        st.session_state[k] = []
                        w_key = k.replace("saved_", "widget_")
                        if w_key in st.session_state:
                            del st.session_state[w_key]
                    st.rerun()

        df_clientes_filtrado = df_clientes.copy()
        if sel_pais_cli:
            df_clientes_filtrado = df_clientes_filtrado[df_clientes_filtrado["País"].isin(sel_pais_cli)]
        if sel_est_cli:
            df_clientes_filtrado = df_clientes_filtrado[df_clientes_filtrado["Estado"].isin(sel_est_cli)]
        if sel_cid_cli:
            df_clientes_filtrado = df_clientes_filtrado[df_clientes_filtrado["Cidade"].isin(sel_cid_cli)]
        if sel_gen_cli:
            df_clientes_filtrado = df_clientes_filtrado[df_clientes_filtrado["Gênero"].isin(sel_gen_cli)]
        if sel_faixa_cli:
            df_clientes_filtrado = df_clientes_filtrado[df_clientes_filtrado["Faixa Etária"].isin(sel_faixa_cli)]
        if sel_canal_cli:
            df_clientes_filtrado = df_clientes_filtrado[df_clientes_filtrado["Canal de Aquisição"].isin(sel_canal_cli)]

        st.dataframe(
            df_clientes_filtrado,
            column_config={
                "Data de Cadastro": st.column_config.DateColumn("Data de Cadastro", format="DD/MM/YYYY"),
                "Quantidade de Usuários": st.column_config.NumberColumn("Quantidade de Usuários", format="%d"),
                "Quantidade de Pedidos": st.column_config.NumberColumn("Quantidade de Pedidos", format="%d"),
                "Faturamento Gerado (US$)": st.column_config.NumberColumn("Faturamento Gerado (US$)", format="$ %.2f"),
                "Custo Total do Cliente (US$)": st.column_config.NumberColumn("Custo Total do Cliente (US$)", format="$ %.2f"),
                "LTV / Lucro Gerado (US$)": st.column_config.NumberColumn("LTV / Lucro Gerado (US$)", format="$ %.2f"),
            },
            use_container_width=True,
            hide_index=True,
        )

        detalhes_filtros_c = [f"Período: {data_inicio_c.strftime('%d/%m/%Y')} a {data_fim_c.strftime('%d/%m/%Y')}"]
        if sel_pais_cli:
            detalhes_filtros_c.append(f"País: {', '.join(sel_pais_cli)}")
        if sel_est_cli:
            detalhes_filtros_c.append(f"Estado: {', '.join(sel_est_cli)}")
        if sel_cid_cli:
            detalhes_filtros_c.append(f"Cidade: {', '.join(sel_cid_cli)}")
        if sel_gen_cli:
            detalhes_filtros_c.append(f"Gênero: {', '.join(sel_gen_cli)}")
        if sel_faixa_cli:
            detalhes_filtros_c.append(f"Faixa Etária: {', '.join(sel_faixa_cli)}")
        if sel_canal_cli:
            detalhes_filtros_c.append(f"Canal: {', '.join(sel_canal_cli)}")

        texto_clientes_a1 = "Filtros aplicados: " + " | ".join(detalhes_filtros_c)

        st.download_button(
            label="📥 Exportar em Excel (.xlsx)",
            data=lambda: gerar_excel(df_clientes_filtrado, texto_clientes_a1, nome_aba="Clientes"),
            file_name="clientes.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.warning("Nenhum cliente encontrado para o período de cadastro selecionado.")

    # ==============================================================================
    # EXPORTAÇÃO CONSOLIDADA NA BARRA LATERAL (MOVIDA PARA O FINAL!)
    # ==============================================================================
    with st.sidebar:
        st.markdown("---")
        st.subheader("📦 Exportação Consolidada")
        st.caption(
            "Baixe todos os relatórios filtrados em uma única planilha Excel com abas separadas."
        )
        st.download_button(
            label="📥 Baixar Relatório Completo (.xlsx)",
            data=lambda: gerar_excel_relatorio_completo(
                df_consolidado_excel,
                texto_params,
                df_eventos_filtrado,
                texto_eventos_a1,
                df_pedidos_filtrado,
                texto_pedidos_a1,
                df_clientes_filtrado,
                texto_clientes_a1,
            ),
            file_name="relatorio_analitico_geral.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )