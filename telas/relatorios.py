import io
import streamlit as st
import pandas as pd
import numpy as np
import openpyxl

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
    e adiciona a linha de observação dos parâmetros no rodapé.
    """
    buffer = io.BytesIO()
    # Prepara o texto formatado dos parâmetros
    texto_params = "Parâmetros utilizados na simulação: " + "; ".join(
        [f"{k} = {v}" for k, v in parametros_dict.items()]
    )

    df_export = df_dados.copy()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_export.to_excel(writer, sheet_name="Simulacao_Clusters", index=False)
        worksheet = writer.sheets["Simulacao_Clusters"]
        linha_rodape = len(df_export) + 3  # Deixa uma linha em branco antes do rodapé
        worksheet.cell(row=linha_rodape, column=1, value=texto_params)

    buffer.seek(0)
    return buffer


def renderizar(con):
    st.title("📊 Visão Analítica do Negócio & Relatórios Executivos")
    st.caption(
        "Consolidação estratégica de segmentação, simulações, tráfego web, vendas e perfil de clientes."
    )

    # ==============================================================================
    # PARTE 1: SEGMENTAÇÃO DE CLIENTES & PARECER DA ÚLTIMA SIMULAÇÃO
    # ==============================================================================
    st.markdown("---")
    st.subheader("🎯 Parecer da Simulação e Diagnóstico de Clusters")

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

        # Resumo baseline idêntico ao simulador.py
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

        # Tabela 1A: Baseline K-Means Formatada em PT-BR
        st.markdown("##### 📋 Dados Atuais dos Segmentos")
        df_1a_display = pd.DataFrame(
            {
                "Segmento (Cluster)": resumo_clusters["cluster_nome"],
                "Total de Clientes": resumo_clusters["Total_Clientes"].apply(
                    lambda x: formata_br(x, decimais=0)
                ),
                "Recência Média (Dias)": resumo_clusters["Recencia_Media"].apply(
                    lambda x: formata_br(x, decimais=1)
                ),
                "Frequência Média (Pedidos)": resumo_clusters["Frequencia_Media"].apply(
                    lambda x: formata_br(x, decimais=2)
                ),
                "Ticket Médio (US$)": resumo_clusters["Ticket_Medio"].apply(
                    lambda x: formata_br(x, decimais=2)
                ),
                "Receita Total (US$)": resumo_clusters["Valor_Total"].apply(
                    lambda x: formata_br(x, decimais=2)
                ),
                "Lucro Total (US$)": resumo_clusters["Lucro_Total"].apply(
                    lambda x: formata_br(x, decimais=2)
                ),
            }
        )
        st.dataframe(df_1a_display, use_container_width=True, hide_index=True)

        # Tabela 1B: Resultado Simulado por Cluster Formatado em PT-BR
        st.markdown("##### 🚀 Resultado Simulado por Cluster")
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

            # Fórmulas de resposta e simulação do modelo
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

            # Tabela 1B exibida em tela
            dados_simulados_display.append(
                {
                    "Segmento (Cluster)": seg,
                    "Taxa Resposta Efetiva (%)": formata_br(
                        taxa_conversao_efetiva, decimais=1
                    ),
                    "Clientes Convertidos": formata_br(clientes_impactados, decimais=0),
                    "Receita Projetada (US$)": formata_br(
                        receita_bruta, decimais=2
                    ),
                    "Custo Total (US$)": formata_br(custo_total, decimais=2),
                    "Lucro Líquido Proj. (US$)": formata_br(
                        lucro_liquido, decimais=2
                    ),
                    "ROMI (x:1)": formata_br(ratio_receita, decimais=2),
                    "Diagnóstico": diag,
                }
            )

            # UNIFICA BASELINE + SIMULAÇÃO NA MESMA LINHA PARA O EXCEL
            dados_consolidados_excel.append(
                {
                    "Segmento (Cluster)": seg,
                    "Total de Clientes (Atual)": formata_br(n_clientes, decimais=0),
                    "Recência Média (Dias)": formata_br(recencia_seg, decimais=1, sufixo="d"),
                    "Frequência Média (Pedidos)": formata_br(
                        row_cluster["Frequencia_Media"], decimais=2
                    ),
                    "Ticket Médio (US$)": formata_br(ticket_medio, prefixo="US$ ", decimais=2),
                    "Receita Histórica Total (US$)": formata_br(
                        row_cluster["Valor_Total"], prefixo="US$ ", decimais=2
                    ),
                    "Lucro Histórico Total (US$)": formata_br(
                        row_cluster["Lucro_Total"], prefixo="US$ ", decimais=2
                    ),
                    "Taxa Resposta Efetiva (%)": formata_br(
                        taxa_conversao_efetiva, sufixo="%", decimais=1
                    ),
                    "Clientes Convertidos (Simulado)": formata_br(clientes_impactados, decimais=0),
                    "Receita Projetada (US$)": formata_br(
                        receita_bruta, prefixo="US$ ", decimais=2
                    ),
                    "Custo Total Simulado (US$)": formata_br(
                        custo_total, prefixo="US$ ", decimais=2
                    ),
                    "Lucro Líquido Proj. (US$)": formata_br(
                        lucro_liquido, prefixo="US$ ", decimais=2
                    ),
                    "ROMI (x:1)": formata_br(ratio_receita, sufixo=":1", decimais=2),
                    "Diagnóstico": diag,
                }
            )

        df_simulacao_resultado = pd.DataFrame(dados_simulados_display)
        st.dataframe(df_simulacao_resultado, use_container_width=True, hide_index=True)

        # DataFrame Consolidado unificando as duas tabelas
        df_consolidado_excel = pd.DataFrame(dados_consolidados_excel)

        # Botão de Exportação do Excel Unificado
        excel_bytes = gerar_excel_com_observacao(df_consolidado_excel, dict_params)
        st.download_button(
            label="📥 Exportar Simulação Completa em Excel (.xlsx)",
            data=excel_bytes,
            file_name="relatorio_simulacao_clusters_completo.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # ==============================================================================
    # PARTE 2: ANALÍTICO DE TRÁFEGO (EVENTOS WEB)
    # ==============================================================================
    st.markdown("---")
    st.subheader("🌐 Analítico Geral de Tráfego Web")
    st.caption("Visão detalhada de todos os eventos de navegação no site.")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        data_inicio_e = st.date_input("Data Inicial (Eventos)", pd.to_datetime("2023-01-01"))
    with col_f2:
        data_fim_e = st.date_input("Data Final (Eventos)", pd.to_datetime("2024-12-31"))

    query_eventos = f"""
        SELECT 
            TRY_CAST(created_at AS TIMESTAMP) AS "Data e Hora",
            event_type AS "Tipo de Ação",
            traffic_source AS "Origem do Tráfego",
            browser AS "Navegador",
            uri AS "Página Acessada (URI)",
            sequence_number AS "Ordem no Clique da Sessão",
            city AS "Cidade",
            state AS "Estado"
        FROM events
        WHERE TRY_CAST(created_at AS DATE) BETWEEN '{data_inicio_e}' AND '{data_fim_e}'
        ORDER BY created_at DESC
        LIMIT 5000
    """

    try:
        df_eventos = con.execute(query_eventos).df()
        if not df_eventos.empty:
            df_eventos["Ordem no Clique da Sessão"] = df_eventos["Ordem no Clique da Sessão"].apply(
                lambda x: formata_br(x, decimais=0)
            )
    except Exception:
        df_eventos = pd.DataFrame()

    if not df_eventos.empty:
        st.dataframe(df_eventos, use_container_width=True, hide_index=True)
        csv_eventos = df_eventos.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Exportar Analítico de Tráfego (CSV)",
            data=csv_eventos,
            file_name="analitico_trafego_eventos.csv",
            mime="text/csv",
        )
    else:
        st.warning("Nenhum evento de tráfego encontrado para o período selecionado.")

    # ==============================================================================
    # PARTE 3: ANALÍTICO DE PEDIDOS E COMPRAS DE PRODUTOS
    # ==============================================================================
    st.markdown("---")
    st.subheader("🛍️ Analítico Completo de Pedidos e Vendas de Produtos")
    st.caption(
        "Detalhamento comercial e logístico das vendas agrupado por item/categoria, omitindo dados dos clientes."
    )

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        data_inicio_p = st.date_input("Data Inicial (Pedidos)", pd.to_datetime("2023-01-01"))
    with col_p2:
        data_fim_p = st.date_input("Data Final (Pedidos)", pd.to_datetime("2024-12-31"))

    query_pedidos = f"""
        SELECT 
            TRY_CAST(oi.created_at AS TIMESTAMP) AS "Data do Pedido",
            p.category AS "Categoria",
            p.name AS "Nome do Produto",
            p.brand AS "Marca",
            p.department AS "Departamento",
            oi.status AS "Status do Item",
            COUNT(oi.id) AS "Quantidade Vendida",
            ROUND(SUM(oi.sale_price), 2) AS "Receita Total (US$)",
            ROUND(SUM(p.cost), 2) AS "Custo Total (US$)",
            ROUND(SUM(oi.sale_price - p.cost), 2) AS "Margem de Lucro Bruto (US$)"
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE TRY_CAST(oi.created_at AS DATE) BETWEEN '{data_inicio_p}' AND '{data_fim_p}'
        GROUP BY 1, 2, 3, 4, 5, 6
        ORDER BY "Data do Pedido" DESC
        LIMIT 5000
    """

    try:
        df_pedidos = con.execute(query_pedidos).df()
        if not df_pedidos.empty:
            df_pedidos["Quantidade Vendida"] = df_pedidos["Quantidade Vendida"].apply(
                lambda x: formata_br(x, decimais=0)
            )
            df_pedidos["Receita Total (US$)"] = df_pedidos["Receita Total (US$)"].apply(
                lambda x: formata_br(x, prefixo="US$ ", decimais=2)
            )
            df_pedidos["Custo Total (US$)"] = df_pedidos["Custo Total (US$)"].apply(
                lambda x: formata_br(x, prefixo="US$ ", decimais=2)
            )
            df_pedidos["Margem de Lucro Bruto (US$)"] = df_pedidos[
                "Margem de Lucro Bruto (US$)"
            ].apply(lambda x: formata_br(x, prefixo="US$ ", decimais=2))
    except Exception:
        df_pedidos = pd.DataFrame()

    if not df_pedidos.empty:
        st.dataframe(df_pedidos, use_container_width=True, hide_index=True)
        csv_pedidos = df_pedidos.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Exportar Analítico de Pedidos (CSV)",
            data=csv_pedidos,
            file_name="analitico_pedidos_vendas.csv",
            mime="text/csv",
        )
    else:
        st.warning("Nenhum pedido encontrado para o período selecionado.")

    # ==============================================================================
    # PARTE 4: ANALÍTICO DE CLIENTES (ANONIMIZADO)
    # ==============================================================================
    st.markdown("---")
    st.subheader("👥 Analítico Demográfico e Perfil de Valor de Clientes")
    st.caption(
        "Visão sumarizada do comportamento de compras e LTV por perfil demográfico e canal, sem exposição de IDs ou nomes."
    )

    col_u1, col_u2 = st.columns(2)
    with col_u1:
        data_inicio_u = st.date_input("Data Inicial (Cadastro)", pd.to_datetime("2020-01-01"))
    with col_u2:
        data_fim_u = st.date_input("Data Final (Cadastro)", pd.to_datetime("2024-12-31"))

    query_clientes = f"""
        SELECT 
            TRY_CAST(u.created_at AS DATE) AS "Data de Cadastro",
            u.gender AS "Gênero",
            u.age AS "Idade",
            u.state AS "Estado",
            u.country AS "País",
            u.traffic_source AS "Canal de Aquisição",
            COUNT(DISTINCT o.order_id) AS "Quantidade de Compras",
            ROUND(COALESCE(SUM(oi.sale_price), 0), 2) AS "Faturamento Gerado (US$)",
            ROUND(COALESCE(SUM(p.cost), 0), 2) AS "Custo Total do Cliente (US$)",
            ROUND(COALESCE(SUM(oi.sale_price - p.cost), 0), 2) AS "LTV / Lucro Gerado (US$)"
        FROM users u
        LEFT JOIN orders o ON u.id = o.user_id AND o.status = 'Complete'
        LEFT JOIN order_items oi ON o.order_id = oi.order_id
        LEFT JOIN products p ON oi.product_id = p.id
        WHERE TRY_CAST(u.created_at AS DATE) BETWEEN '{data_inicio_u}' AND '{data_fim_u}'
        GROUP BY u.id, u.created_at, u.gender, u.age, u.state, u.country, u.traffic_source
        ORDER BY "Faturamento Gerado (US$)" DESC
        LIMIT 5000
    """

    try:
        df_clientes = con.execute(query_clientes).df()
        if not df_clientes.empty:
            df_clientes["Idade"] = df_clientes["Idade"].apply(lambda x: formata_br(x, decimais=0))
            df_clientes["Quantidade de Compras"] = df_clientes["Quantidade de Compras"].apply(
                lambda x: formata_br(x, decimais=0)
            )
            df_clientes["Faturamento Gerado (US$)"] = df_clientes["Faturamento Gerado (US$)"].apply(
                lambda x: formata_br(x, prefixo="US$ ", decimais=2)
            )
            df_clientes["Custo Total do Cliente (US$)"] = df_clientes[
                "Custo Total do Cliente (US$)"
            ].apply(lambda x: formata_br(x, prefixo="US$ ", decimais=2))
            df_clientes["LTV / Lucro Gerado (US$)"] = df_clientes["LTV / Lucro Gerado (US$)"].apply(
                lambda x: formata_br(x, prefixo="US$ ", decimais=2)
            )
    except Exception:
        df_clientes = pd.DataFrame()

    if not df_clientes.empty:
        st.dataframe(df_clientes, use_container_width=True, hide_index=True)
        csv_clientes = df_clientes.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Exportar Analítico de Clientes (CSV)",
            data=csv_clientes,
            file_name="analitico_perfil_clientes.csv",
            mime="text/csv",
        )
    else:
        st.warning("Nenhum cliente encontrado para o período de cadastro selecionado.")