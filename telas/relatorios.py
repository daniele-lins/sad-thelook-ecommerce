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

def gerar_excel_eventos(df_dados, texto_filtros):
    """
    Gera a planilha Excel com o resumo dos filtros na célula A1
    e a tabela de dados iniciando na célula A2 (linha 2).
    """
    buffer = io.BytesIO()
    df_export = df_dados.copy()

    # Formata datas para o padrão brasileiro DD/MM/YYYY
    if "Data" in df_export.columns and pd.api.types.is_datetime64_any_dtype(
        df_export["Data"]
    ):
        df_export["Data"] = df_export["Data"].dt.strftime("%d/%m/%Y")

    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        # 1. Escreve a tabela a partir da célula A2 (startrow=1)
        df_export.to_excel(
            writer, sheet_name="Analitico", index=False, startrow=1
        )

        # 2. Escreve a mensagem dos filtros exatamente na célula A1 (linha 0, coluna 0)
        worksheet = writer.sheets["Analitico"]
        worksheet.write(0, 0, texto_filtros)

    buffer.seek(0)
    return buffer

@st.cache_data(show_spinner="Carregando dados de tráfego...")
def buscar_dados_eventos(_con, data_inicio, data_fim):
    """
    Executa a query de eventos e armazena o resultado em cache.
    Só reexecuta no DuckDB se as datas inicial ou final mudarem.
    """
    query = f"""
        WITH mapa_localizacao AS (
            SELECT DISTINCT city, state, country 
            FROM users 
            WHERE country IS NOT NULL AND LOWER(country) != 'não informado'
        )
        SELECT 
            TRY_CAST(e.created_at AS date) AS "Data",
            CASE e.event_type
                WHEN 'home' THEN 'Página Inicial'
                WHEN 'department' THEN 'Departamento'
                WHEN 'product' THEN 'Produto'
                WHEN 'cart' THEN 'Carrinho'
                WHEN 'purchase' THEN 'Compra'
                WHEN 'cancel' THEN 'Cancelamento'
                ELSE e.event_type
            END as "Etapa",
            e.traffic_source AS "Origem do Tráfego",
            COALESCE(
                (SELECT ANY_VALUE(m.country) FROM mapa_localizacao m WHERE m.state = e.state AND m.city = e.city),
                (SELECT ANY_VALUE(m.country) FROM mapa_localizacao m WHERE m.state = e.state),
                (SELECT ANY_VALUE(m.country) FROM mapa_localizacao m WHERE m.city = e.city),
                'Não Informado'
            ) AS "País",
            COALESCE(e.state, 'Não Informado') AS "Estado",
            COALESCE(e.city, 'Não Informado') AS "Cidade",
            COUNT(DISTINCT e.session_id) as "Sessões",
            COUNT(DISTINCT e.user_id) as "Usuários"
        FROM events e
        WHERE TRY_CAST(e.created_at AS DATE) BETWEEN '{data_inicio}' AND '{data_fim}'
        GROUP BY ALL
        ORDER BY "Data" DESC
    """
    return _con.execute(query).df()


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
            label="📥 Exportar em Excel (.xlsx)",
            data=excel_bytes,
            file_name="relatorio_simulacao_clusters_completo.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # ==============================================================================
    # PARTE 2: ANALÍTICO GERAL DE TRÁFEGO WEB (EXPORTAÇÃO EXCEL COM A1 CONFIGURADA)
    # ==============================================================================
    st.markdown("---")
    st.subheader("🌐 Analítico Geral de Tráfego Web")
    st.caption(
        "Visão agregada do funil de navegação, origem de tráfego e localização por sessão e usuário."
    )

    col_f1, col_f2, col_f3 = st.columns([1, 1, 1])
    with col_f1:
        data_inicio_e = st.date_input("Data Inicial (Eventos)", pd.to_datetime("2023-01-01"))
    with col_f2:
        data_fim_e = st.date_input("Data Final (Eventos)", pd.to_datetime("2024-12-31"))

    # Busca em cache para não recarregar a query em cliques acidentais
    try:
        df_eventos = buscar_dados_eventos(con, data_inicio_e, data_fim_e)
    except Exception:
        df_eventos = pd.DataFrame()

    if not df_eventos.empty:
        df_eventos["Data"] = pd.to_datetime(df_eventos["Data"])

        # 1. Inicialização de chaves no session_state para persistência
        if "saved_filter_pais" not in st.session_state:
            st.session_state["saved_filter_pais"] = []
        if "saved_filter_estado" not in st.session_state:
            st.session_state["saved_filter_estado"] = []
        if "saved_filter_cidade" not in st.session_state:
            st.session_state["saved_filter_cidade"] = []
        if "saved_filter_etapa" not in st.session_state:
            st.session_state["saved_filter_etapa"] = []
        if "saved_filter_origem" not in st.session_state:
            st.session_state["saved_filter_origem"] = []

        # 2. Leitura dos estados atuais
        sel_pais_atual = st.session_state["saved_filter_pais"]
        sel_estado_atual = st.session_state["saved_filter_estado"]
        sel_cidade_atual = st.session_state["saved_filter_cidade"]
        sel_etapa_atual = st.session_state["saved_filter_etapa"]
        sel_origem_atual = st.session_state["saved_filter_origem"]

        # 3. Cálculo das Opções Dinâmicas em Cascata
        df_p = df_eventos.copy()
        if sel_estado_atual:
            df_p = df_p[df_p["Estado"].isin(sel_estado_atual)]
        if sel_cidade_atual:
            df_p = df_p[df_p["Cidade"].isin(sel_cidade_atual)]
        if sel_etapa_atual:
            df_p = df_p[df_p["Etapa"].isin(sel_etapa_atual)]
        if sel_origem_atual:
            df_p = df_p[df_p["Origem do Tráfego"].isin(sel_origem_atual)]
        opcoes_pais = sorted(df_p["País"].dropna().unique().tolist())

        df_e = df_eventos.copy()
        if sel_pais_atual:
            df_e = df_e[df_e["País"].isin(sel_pais_atual)]
        if sel_cidade_atual:
            df_e = df_e[df_e["Cidade"].isin(sel_cidade_atual)]
        if sel_etapa_atual:
            df_e = df_e[df_e["Etapa"].isin(sel_etapa_atual)]
        if sel_origem_atual:
            df_e = df_e[df_e["Origem do Tráfego"].isin(sel_origem_atual)]
        opcoes_estado = sorted(df_e["Estado"].dropna().unique().tolist())

        df_c = df_eventos.copy()
        if sel_pais_atual:
            df_c = df_c[df_c["País"].isin(sel_pais_atual)]
        if sel_estado_atual:
            df_c = df_c[df_c["Estado"].isin(sel_estado_atual)]
        if sel_etapa_atual:
            df_c = df_c[df_c["Etapa"].isin(sel_etapa_atual)]
        if sel_origem_atual:
            df_c = df_c[df_c["Origem do Tráfego"].isin(sel_origem_atual)]
        opcoes_cidade = sorted(df_c["Cidade"].dropna().unique().tolist())

        df_et = df_eventos.copy()
        if sel_pais_atual:
            df_et = df_et[df_et["País"].isin(sel_pais_atual)]
        if sel_estado_atual:
            df_et = df_et[df_et["Estado"].isin(sel_estado_atual)]
        if sel_cidade_atual:
            df_et = df_et[df_et["Cidade"].isin(sel_cidade_atual)]
        if sel_origem_atual:
            df_et = df_et[df_et["Origem do Tráfego"].isin(sel_origem_atual)]
        opcoes_etapa = sorted(df_et["Etapa"].dropna().unique().tolist())

        df_o = df_eventos.copy()
        if sel_pais_atual:
            df_o = df_o[df_o["País"].isin(sel_pais_atual)]
        if sel_estado_atual:
            df_o = df_o[df_o["Estado"].isin(sel_estado_atual)]
        if sel_cidade_atual:
            df_o = df_o[df_o["Cidade"].isin(sel_cidade_atual)]
        if sel_etapa_atual:
            df_o = df_o[df_o["Etapa"].isin(sel_etapa_atual)]
        opcoes_origem = sorted(df_o["Origem do Tráfego"].dropna().unique().tolist())

        # Sanitização de escolhas
        st.session_state["saved_filter_pais"] = [
            x for x in st.session_state["saved_filter_pais"] if x in opcoes_pais
        ]
        st.session_state["saved_filter_estado"] = [
            x for x in st.session_state["saved_filter_estado"] if x in opcoes_estado
        ]
        st.session_state["saved_filter_cidade"] = [
            x for x in st.session_state["saved_filter_cidade"] if x in opcoes_cidade
        ]
        st.session_state["saved_filter_etapa"] = [
            x for x in st.session_state["saved_filter_etapa"] if x in opcoes_etapa
        ]
        st.session_state["saved_filter_origem"] = [
            x for x in st.session_state["saved_filter_origem"] if x in opcoes_origem
        ]

        st.session_state["widget_filter_pais"] = st.session_state["saved_filter_pais"]
        st.session_state["widget_filter_estado"] = st.session_state["saved_filter_estado"]
        st.session_state["widget_filter_cidade"] = st.session_state["saved_filter_cidade"]
        st.session_state["widget_filter_etapa"] = st.session_state["saved_filter_etapa"]
        st.session_state["widget_filter_origem"] = st.session_state["saved_filter_origem"]

        # 4. Interface Popover + Botão Reset
        with col_f3:
            st.write("")
            st.write("")
            with st.popover("⚙️ Filtrar por Colunas"):
                st.markdown("**Filtros dinâmicos (deixe vazio para mostrar tudo):**")
                sel_pais = st.multiselect(
                    "País:",
                    options=opcoes_pais,
                    key="widget_filter_pais",
                    on_change=lambda: st.session_state.update(
                        {"saved_filter_pais": st.session_state["widget_filter_pais"]}
                    ),
                )
                sel_estado = st.multiselect(
                    "Estado:",
                    options=opcoes_estado,
                    key="widget_filter_estado",
                    on_change=lambda: st.session_state.update(
                        {"saved_filter_estado": st.session_state["widget_filter_estado"]}
                    ),
                )
                sel_cidade = st.multiselect(
                    "Cidade:",
                    options=opcoes_cidade,
                    key="widget_filter_cidade",
                    on_change=lambda: st.session_state.update(
                        {"saved_filter_cidade": st.session_state["widget_filter_cidade"]}
                    ),
                )
                sel_etapa = st.multiselect(
                    "Etapa do Funil:",
                    options=opcoes_etapa,
                    key="widget_filter_etapa",
                    on_change=lambda: st.session_state.update(
                        {"saved_filter_etapa": st.session_state["widget_filter_etapa"]}
                    ),
                )
                sel_origem = st.multiselect(
                    "Origem do Tráfego:",
                    options=opcoes_origem,
                    key="widget_filter_origem",
                    on_change=lambda: st.session_state.update(
                        {"saved_filter_origem": st.session_state["widget_filter_origem"]}
                    ),
                )

                st.markdown("---")
                if st.button("🔄 Resetar Filtros", use_container_width=True):
                    st.session_state["saved_filter_pais"] = []
                    st.session_state["saved_filter_estado"] = []
                    st.session_state["saved_filter_cidade"] = []
                    st.session_state["saved_filter_etapa"] = []
                    st.session_state["saved_filter_origem"] = []
                    for k in [
                        "widget_filter_pais",
                        "widget_filter_estado",
                        "widget_filter_cidade",
                        "widget_filter_etapa",
                        "widget_filter_origem",
                    ]:
                        if k in st.session_state:
                            del st.session_state[k]
                    st.rerun()

        # 5. Aplicação final dos filtros
        df_filtrado = df_eventos.copy()
        if sel_pais:
            df_filtrado = df_filtrado[df_filtrado["País"].isin(sel_pais)]
        if sel_estado:
            df_filtrado = df_filtrado[df_filtrado["Estado"].isin(sel_estado)]
        if sel_cidade:
            df_filtrado = df_filtrado[df_filtrado["Cidade"].isin(sel_cidade)]
        if sel_etapa:
            df_filtrado = df_filtrado[df_filtrado["Etapa"].isin(sel_etapa)]
        if sel_origem:
            df_filtrado = df_filtrado[df_filtrado["Origem do Tráfego"].isin(sel_origem)]

        # Renderização em tela
        st.dataframe(
            df_filtrado,
            column_config={
                "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                "Sessões": st.column_config.NumberColumn("Sessões", format="%d"),
                "Usuários": st.column_config.NumberColumn("Usuários", format="%d"),
            },
            use_container_width=True,
            hide_index=True,
        )

        # 6. Montagem do texto detalhado de filtros para a célula A1 do Excel
        detalhes_filtros = [
            f"Período: {data_inicio_e.strftime('%d/%m/%Y')} a {data_fim_e.strftime('%d/%m/%Y')}"
        ]
        if sel_pais:
            detalhes_filtros.append(f"País: {', '.join(sel_pais)}")
        if sel_estado:
            detalhes_filtros.append(f"Estado: {', '.join(sel_estado)}")
        if sel_cidade:
            detalhes_filtros.append(f"Cidade: {', '.join(sel_cidade)}")
        if sel_etapa:
            detalhes_filtros.append(f"Etapa: {', '.join(sel_etapa)}")
        if sel_origem:
            detalhes_filtros.append(f"Origem: {', '.join(sel_origem)}")

        texto_filtros_a1 = "Filtros aplicados: " + " | ".join(detalhes_filtros)

        # Botão único: inerte nas mudanças de filtros/telas e executado no clique
        st.download_button(
            label="📥 Exportar em Excel (.xlsx)",
            data=lambda: gerar_excel_eventos(df_filtrado, texto_filtros_a1),
            file_name="eventos.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    else:
        st.warning("Nenhum evento de tráfego encontrado para o período selecionado.")

    # ==============================================================================
    # PARTE 4: ANALÍTICO DE CLIENTES (ANONIMIZADO)
    # ==============================================================================
    st.markdown("---")
    st.subheader("👥 Analítico Demográfico e Perfil de Valor de Clientes")
    st.caption(
        "Visão sumarizada do comportamento de compras e LTV por perfil demográfico e canal, sem exposição de IDs ou nomes."
    )

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