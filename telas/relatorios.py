import datetime
import numpy as np
import pandas as pd
import streamlit as st


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


@st.cache_data(ttl=300)
def obter_limites_datas(_con):
    """Obtém a data mínima e máxima presentes na base de pedidos concluídos."""
    query = """
        SELECT 
            MIN(TRY_CAST(created_at AS DATE)) as min_date, 
            MAX(TRY_CAST(created_at AS DATE)) as max_date 
        FROM order_items 
        WHERE status = 'Complete'
    """
    df = _con.execute(query).df()
    min_d = df.iloc[0]["min_date"]
    max_d = df.iloc[0]["max_date"]

    if pd.isna(min_d):
        min_d = datetime.date(2019, 1, 1)
    if pd.isna(max_d):
        max_d = datetime.date(2024, 1, 1)

    return min_d, max_d


@st.cache_data(ttl=300)
def gerar_diagnostico_periodo(_con, dt_inicio, dt_fim):
    """Consulta consolidada de vendas e margem no DuckDB para a janela temporal selecionada."""
    query = f"""
        SELECT 
            COUNT(DISTINCT oi.order_id) AS total_pedidos, 
            COUNT(DISTINCT oi.user_id) AS total_clientes, 
            COALESCE(SUM(oi.sale_price), 0) AS receita_total, 
            COALESCE(SUM(p.cost), 0) AS custo_total, 
            COALESCE(SUM(oi.sale_price - p.cost), 0) AS lucro_bruto, 
            COALESCE(AVG(oi.sale_price), 0) AS ticket_medio_item 
        FROM order_items oi 
        JOIN products p ON oi.product_id = p.id 
        WHERE oi.status = 'Complete' 
          AND TRY_CAST(oi.created_at AS DATE) BETWEEN '{dt_inicio}' AND '{dt_fim}'
    """
    return _con.execute(query).df().iloc[0]


@st.cache_data(ttl=300)
def carregar_rfm_periodo(_con, dt_inicio, dt_fim):
    """Extrai métricas comportamentais RFM dos clientes que compraram na janela temporal."""
    query = f"""
        WITH rfm AS (
            SELECT 
                oi.user_id, 
                DATEDIFF('day', MAX(TRY_CAST(oi.created_at AS DATE)), '{dt_fim}') AS recencia, 
                COUNT(DISTINCT oi.order_id) AS frequencia, 
                SUM(oi.sale_price) AS valor_monetario 
            FROM order_items oi 
            WHERE oi.status = 'Complete' 
              AND TRY_CAST(oi.created_at AS DATE) BETWEEN '{dt_inicio}' AND '{dt_fim}' 
            GROUP BY oi.user_id 
            HAVING SUM(oi.sale_price) > 0
        )
        SELECT 
            COUNT(user_id) as total_compradores, 
            COALESCE(AVG(recencia), 0) as recencia_media, 
            COALESCE(AVG(frequencia), 0) as frequencia_media, 
            COALESCE(AVG(valor_monetario), 0) as gasto_medio, 
            COUNT(CASE WHEN recencia > 60 THEN 1 END) as qtd_inativos_60d, 
            COUNT(CASE WHEN recencia <= 30 THEN 1 END) as qtd_ativos_30d 
        FROM rfm
    """
    return _con.execute(query).df().iloc[0]


def renderizar(con):
    st.header("📄 Relatório Executivo & Prescrições do SAD")
    st.markdown(
        """
        Este módulo consolida a **saúde financeira do e-commerce** e gera **diretrizes estratégicas recomendadas dinamicamente**, adaptando os pareceres conforme o filtro de período selecionado pelo gestor.
        """
    )

    # ====================================================
    # FILTRO DINÂMICO DE PERÍODO (BARRA DE CONTROLE)
    # ====================================================
    min_data_db, max_data_db = obter_limites_datas(con)

    st.markdown("---")
    st.markdown("### 🗓️ Seleção do Período de Análise")
    col_f1, col_f2, col_f3 = st.columns([1.2, 1, 1])

    with col_f1:
        opcao_periodo = st.selectbox(
            "Atalho de Intervalo",
            options=[
                "Todo o Histórico",
                "Últimos 30 Dias",
                "Últimos 90 Dias",
                "Ano de 2023",
                "Personalizado",
            ],
            index=0,
        )

        if opcao_periodo == "Todo o Histórico":
            dt_inicio = min_data_db
            dt_fim = max_data_db
        elif opcao_periodo == "Últimos 30 Dias":
            dt_fim = max_data_db
            dt_inicio = max_data_db - datetime.timedelta(days=30)
        elif opcao_periodo == "Últimos 90 Dias":
            dt_fim = max_data_db
            dt_inicio = max_data_db - datetime.timedelta(days=90)
        elif opcao_periodo == "Ano de 2023":
            dt_inicio = datetime.date(2023, 1, 1)
            dt_fim = datetime.date(2023, 12, 31)
        else:
            dt_inicio = min_data_db
            dt_fim = max_data_db

    with col_f2:
        dt_inicio_sel = st.date_input(
            "Data Inicial",
            value=dt_inicio,
            min_value=min_data_db,
            max_value=max_data_db,
        )

    with col_f3:
        dt_fim_sel = st.date_input(
            "Data Final",
            value=dt_fim,
            min_value=min_data_db,
            max_value=max_data_db,
        )

    if dt_inicio_sel > dt_fim_sel:
        st.error("Erro: A Data Inicial não pode ser posterior à Data Final.")
        return

    # Processamento dos Dados do Período Selecionado
    diag = gerar_diagnostico_periodo(con, dt_inicio_sel, dt_fim_sel)
    rfm = carregar_rfm_periodo(con, dt_inicio_sel, dt_fim_sel)

    # Métricas Derivadas
    receita = diag["receita_total"]
    lucro = diag["lucro_bruto"]
    pedidos = diag["total_pedidos"]
    margem_pct = (lucro / receita * 100) if receita > 0 else 0
    aov = (receita / pedidos) if pedidos > 0 else 0
    compradores = rfm["total_compradores"]

    # ====================================================
    # SEÇÃO 1: QUADRO DE DESEMPENHO OPERACIONAL DO PERÍODO
    # ====================================================
    st.markdown("---")
    st.markdown(
        f"### 📊 Desempenho Operacional ({dt_inicio_sel.strftime('%d/%m/%Y')} a {dt_fim_sel.strftime('%d/%m/%Y')})"
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Receita Bruta", formata_br(receita, prefixo="US$ "))
    c2.metric("Lucro Bruto", formata_br(lucro, prefixo="US$ "))
    c3.metric("Margem Bruta Média", f"{formata_br(margem_pct, decimais=1)}%")
    c4.metric("Ticket Médio (AOV)", formata_br(aov, prefixo="US$ "))

    st.markdown("---")

    # ====================================================
    # SEÇÃO 2: RECOMENDAÇÕES PRESCRITIVAS DINÂMICAS DO SAD
    # ====================================================
    st.markdown("### 🎯 Diretrizes Estratégicas Adaptativas (Motor SAD)")
    st.markdown(
        "As prescrições abaixo são **recalculadas em tempo real** de acordo com os indicadores do período filtrado:"
    )

    # --- REGRA 1: DENSIDADE DE INATIVOS E REATIVAÇÃO ---
    pct_inativos = (
        (rfm["qtd_inativos_60d"] / compradores * 100) if compradores > 0 else 0
    )

    with st.expander(
        "📌 **Diretriz 1: Reativação de Clientes & Retenção de Base**",
        expanded=True,
    ):
        if pct_inativos > 30 or rfm["recencia_media"] > 45:
            st.warning(
                f"🚨 **Alerta de Inatividade Elevada:** No período selecionado, **{formata_br(pct_inativos, decimais=1)}%** dos compradores "
                f"({int(rfm['qtd_inativos_60d'])} clientes) possuem recência superior a 60 dias sem novas compras. A recência média do grupo é "
                f"de **{formata_br(rfm['recencia_media'], decimais=0)} dias**."
            )
            st.markdown(
                "* **Ação Recomendada:** Disparar campanha de reativação imediata oferecendo um cupom promocional limitado a **10%** de desconto. "
                "Exigir ROI mínimo projetado de **5:1** no simulador para evitar prejuízo operacional."
            )
        else:
            st.success(
                f"✅ **Base Ativa e Engajada:** No período filtrado, **{formata_br(100 - pct_inativos, decimais=1)}%** dos compradores "
                f"realizaram pedidos recentemente. A recência média é saudável (**{formata_br(rfm['recencia_media'], decimais=0)} dias**)."
            )
            st.markdown(
                "* **Ação Recomendada:** Focar os esforços em campanhas de incentivo à segunda compra (régua de onboarding) com desconto suave de **5%**, priorizando o cross-selling."
            )

    # --- REGRA 2: RENTABILIDADE E POLÍTICA DE PREÇOS / CROSS-SELLING ---
    with st.expander(
        "📌 **Diretriz 2: Maximização de Margem e Vendas Cruzadas (Cross-Selling)**",
        expanded=True,
    ):
        if margem_pct < 35.0:
            st.error(
                f"⚠️ **Margem de Contribuição Pressionada:** A margem bruta média da janela filtrada é de **{formata_br(margem_pct, decimais=1)}%** "
                "(abaixo da meta de 35%). Conceder descontos irrestritos neste período comprometerá a rentabilidade líquida."
            )
            st.markdown(
                f"* **Ação Recomendada:** Suspender descontos em dinheiro (cash discounts). Substituir por benefícios não monetários (ex: frete grátis condicionado a um valor mínimo de pedido **US$ {formata_br(aov * 1.2, decimais=0)}**)."
            )
        else:
            st.info(
                f"📈 **Margem Bruta Saudável:** A margem média do período é de **{formata_br(margem_pct, decimais=1)}%**, garantindo folga financeira para ações comerciais."
            )
            st.markdown(
                f"* **Ação Recomendada:** Aplicar regras de **Cross-Selling (Associação de Produtos)** recomendando itens complementares do catálogo para elevar o ticket médio atual de **US$ {formata_br(aov)}**."
            )

    # --- REGRA 3: GOVERNANÇA E SIMULAÇÃO OBRIGATÓRIA "WHAT-IF" ---
    with st.expander(
        "📌 **Diretriz 3: Governança Orçamentária via Simulador Preditivo**",
        expanded=True,
    ):
        st.markdown(
            f"""
            * **Diagnóstico da Janela:** O período analisado registrou **{formata_br(pedidos, decimais=0)} pedidos** com faturamento de **{formata_br(receita, prefixo="US$ ")}** e custo de produtos de **{formata_br(diag['custo_total'], prefixo="US$ ")}**.
            * **Regra de Decisão do SAD:** Nenhuma verba publicitária deve ser liberada sem validação prévia no **Simulador Preditivo "What-If"**. O projeto da campanha deve obrigatoriamente demonstrar **Lucro Líquido Incremental > 0** e **ROI superior ao benchmark de 500% (5:1)**.
            """
        )

    # ====================================================
    # SEÇÃO 3: EXPORTAÇÃO DO RELATÓRIO DINÂMICO
    # ====================================================
    st.markdown("---")
    st.markdown("### 📥 Exportação do Relatório Executivo")

    relatorio_texto = f"""====================================================
THELOOK E-COMMERCE - RELATÓRIO EXECUTIVO DO SAD
====================================================
Período Analisado: {dt_inicio_sel.strftime('%d/%m/%Y')} a {dt_fim_sel.strftime('%d/%m/%Y')}
Emissão: Documento Gerado Automaticamente pelo Sistema de Apoio à Decisão

1. DIAGNÓSTICO FINANCEIRO E OPERACIONAL DO PERÍODO:
   - Receita Bruta Acumulada: US$ {formata_br(receita)}
   - Lucro Bruto Comercial: US$ {formata_br(lucro)}
   - Margem Bruta Média: {formata_br(margem_pct, decimais=1)}%
   - Total de Pedidos Concluídos: {int(pedidos)}
   - Ticket Médio por Pedido (AOV): US$ {formata_br(aov)}
   - Clientes Compradores Ativos: {int(compradores)}

2. DIAGNÓSTICO COMPORTAMENTAL (RFM NO PERÍODO):
   - Recência Média da Base: {formata_br(rfm['recencia_media'], decimais=0)} dias
   - Clientes Inativos (> 60 dias): {int(rfm['qtd_inativos_60d'])} ({formata_br(pct_inativos, decimais=1)}%)
   - Frequência Média de Compras: {formata_br(rfm['frequencia_media'], decimais=2)} pedidos/cliente

3. PARECER E PRESCRIÇÕES GERENCIAIS:
   - Reativação: {"Prioridade Alta (Conceder até 10% com cupom)" if pct_inativos > 30 else "Foco em Onboarding (Desconto suave de 5%)"}
   - Política de Preços: {"Restringir descontos e focar em Frete Grátis acima de AOV" if margem_pct < 35 else "Liberdade para ações de Cross-Selling"}
   - Governança: Obrigatória simulação "What-If" no SAD com validação de ROI mínimo.

====================================================
Sistema de Apoio à Decisão (SAD) - TheLook E-commerce
"""

    st.download_button(
        label="📄 Baixar Relatório Executivo Filtrado (TXT)",
        data=relatorio_texto,
        file_name=(
            f"Relatorio_Executivo_TheLook_{dt_inicio_sel.strftime('%Y%m%d')}_{dt_fim_sel.strftime('%Y%m%d')}.txt"
        ),
        mime="text/plain",
        use_container_width=True,
    )