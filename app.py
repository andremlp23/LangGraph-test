import streamlit as st
import pandas as pd
from pathlib import Path
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage
import json

# Configuração da Página
st.set_page_config(page_title="BlocoAI - Analisador Técnico", layout="wide")

st.title("🏗️ BlocoAI: Análise de Orçamentos e Cadernos de Encargos")
st.markdown("---")

# Barra Lateral - Configurações e Uploads
with st.sidebar:
    st.header("Configurações")
    torre_ip = st.text_input("IP da Torre", value="100.105.95.121")
    
    st.header("Documentos")
    ficheiro_excel = st.file_uploader("Carregar Excel (Orçamento)", type=["xlsx"])
    ficheiro_guia = st.file_uploader("Carregar Guia (Matriz de Análise)", type=["pdf", "txt", "png"])

# Inicialização do Modelo
llm = ChatOllama(
    model="qwen3.5:9b",
    base_url=f"http://{torre_ip}:11434",
    temperature=0
)

# Painel Central
col1, col2 = st.columns([1, 1])

if ficheiro_excel and ficheiro_guia:
    if st.button("🚀 Iniciar Varrimento Total"):
        # 1. Simulação de leitura do Excel (aqui usarias as tuas funções read_excel_smart)
        st.info("A processar Excel e a aplicar Guia de Referência...")
        
        # Criaríamos aqui o loop de chunks que fizemos antes
        progresso = st.progress(0)
        
        # Simulação de blocos (Ajustar para a tua lógica real)
        texto_exemplo = "Linhas extraídas do excel..." 
        notas_recolhidas = []
        
        # Exemplo de loop de processamento
        for i in range(1, 6):
            # Aqui vai o llm.invoke(...)
            st.write(f"⚙️ A analisar bloco {i} na torre...")
            progresso.progress(i * 20)
            notas_recolhidas.append(f"Nota do bloco {i}")

        # Consolidação Final
        st.success("Análise concluída!")
        
        tab1, tab2 = st.tabs(["📄 Relatório Técnico", "💻 JSON Export"])
        
        with tab1:
            st.markdown("### Relatório de Engenharia")
            # Aqui imprimes o relatorio_final.content
            st.write("O relatório apareceria aqui com todo o detalhe...")
            
        with tab2:
            st.markdown("### JSON Estruturado")
            json_data = {"projeto": "Fase 2", "dados": notas_recolhidas}
            st.json(json_data)
            st.download_button("Download JSON", data=json.dumps(json_data), file_name="analise.json")

else:
    st.warning("Por favor, carrega ambos os ficheiros na barra lateral para começar.")