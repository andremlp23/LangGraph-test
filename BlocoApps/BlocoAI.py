import streamlit as st
import pandas as pd
import time
import pdfplumber 
import os
import io 
from pathlib import Path
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

# --- 0. CARREGAR AMBIENTE (.env) ---
def carregar_env_local():
    base_dir = Path(__file__).resolve().parent
    candidatos = [base_dir / ".env", base_dir.parent / ".env"]
    for env_path in candidatos:
        if not env_path.exists(): continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            linha = line.strip()
            if not linha or linha.startswith("#") or "=" not in linha: continue
            chave, valor = linha.split("=", 1)
            chave = chave.strip()
            # Limpeza de prefixos como 'export '
            if chave.startswith("export "): chave = chave[len("export "):].strip()
            valor = valor.strip().strip('"').strip("'")
            if chave:
                os.environ[chave] = valor
        return

carregar_env_local()

# --- 1. CONFIGURAÇÃO DA INTERFACE ---
st.set_page_config(page_title="BlocoAI - Sumário Executivo", layout="wide", page_icon="🏗️")

st.sidebar.title("Configurações do Servidor")
modo_execucao = st.sidebar.radio("Ligação", ["API Key", "Local"], index=0)

# Lógica de API Key: Prioridade ao .env, mas permite overwrite no ecrã se necessário
api_key_env = os.getenv("CHATGPT_API_KEY", "")

if modo_execucao == "API Key":
    st.sidebar.caption("Modelo: gpt-4o-mini (Leitura via .env ativa)")
    # Se a key estiver no .env, o campo de texto pode ficar vazio
    api_key_input = st.sidebar.text_input("🔑 API Key (Opcional se definida no .env)", value="", type="password")
    # A chave final é a do input, se houver; caso contrário, a do .env
    api_key_final = api_key_input.strip() if api_key_input.strip() else api_key_env
else:
    torre_ip = st.sidebar.text_input("🌐 IP da Torre", value="100.105.95.121")
    modelo_selecionado = st.sidebar.selectbox("🧠 LLM", ["qwen3.5:9b", "llama3.2:3b"])

# --- 2. LEITURA DE DOCUMENTOS ---
def read_document(file) -> str:
    if file.name.endswith('.pdf'):
        with pdfplumber.open(file) as pdf:
            return "\n".join([f"[Pág: {i+1}] {p.extract_text(layout=True)}" for i, p in enumerate(pdf.pages) if p.extract_text()])
    else:
        xls = pd.ExcelFile(file)
        lines = []
        for sheet in xls.sheet_names:
            df = xls.parse(sheet).astype(str)
            for idx, row in df.iterrows():
                vals = [v.strip() for v in row if v.strip().lower() not in ['nan', 'none', '0.0', '0', '']]
                if len(vals) > 1: lines.append(f"[Linha: {idx+2}] {' | '.join(vals)}")
        return "\n".join(lines)

# --- 3. MOTOR DE SUMARIZAÇÃO EXECUTIVA ---
def extrair_sumario_executivo(texto_integral: str, guia_texto: str, llm):
    tamanho_max_chunk = 15000 
    chunks = [texto_integral[i:i + tamanho_max_chunk] for i in range(0, len(texto_integral), tamanho_max_chunk)]
    
    resumos_finais = []
    st.markdown("### 📡 Gerando Sumário de Auditoria...")
    progresso_bar = st.progress(0)
    status_text = st.empty()

    mensagem_sistema = SystemMessage(
        content=f"""You are a Senior Structural Steel Auditor. 
        Your task is to provide a SYNTHETIC EXECUTIVE SUMMARY of the technical specifications.

        AUDIT PARAMETERS (From Word Document):
        {guia_texto}

        HIERARCHY & CONTEXT:
        - Detect Phase (PH1, PH2...) and Zone (CSA, FSA, DCH...).
        - Group items by category (Structure, Fire, Coatings, Fixings).
        - IDENTIFY RISKS: Highlight clauses about design responsibility, restrictive tolerances, or implicit works.

        OUTPUT STRUCTURE:
        - Organize by [Phase - Project - Zone].
        - Use bullet points for consolidated technical specs.
        - Create a specific section for 'CRITICAL RISKS' in each zone.
        """
    )

    for i, chunk in enumerate(chunks):
        status_text.text(f"🔍 A processar bloco {i+1} de {len(chunks)}...")
        progresso_bar.progress((i + 1) / len(chunks))
        
        try:
            res = llm.invoke([mensagem_sistema, HumanMessage(content=f"Analyze and summarize this BOQ excerpt:\n\n{chunk}")])
            resumos_finais.append(res.content)
            time.sleep(0.5)
        except Exception as e:
            st.error(f"Erro no processamento do bloco {i}: {e}")
            
    return "\n\n".join(resumos_finais)

# --- 4. INTERFACE PRINCIPAL ---
st.title("🏗️ BlocoAI: Sumário Executivo de Auditoria")
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Ficheiro")
    file_uploaded = st.file_uploader("BOQ / Caderno de Encargos", type=["xlsx", "xls", "pdf"])

with col2:
    st.subheader("2. Matriz Técnica (Word)")
    # Texto baseado no teu documento de parâmetros
    guia_padrao = """1. ÂMBITO: Fabrico, Montagem, Engenharia de Ligações.
2. HIERARQUIA: Fases (PH1-3), Zonas (CSA, FSA, DCH).
3. MATERIAIS: Aço (S355), EXC2/3, Normas (EN 1090).
4. PROTEÇÕES: Pintura (Microns), Fogo (R60/120), Jato Sa2.5.
5. RISCOS: Design Responsibility, Furos MEP, Tolerâncias restritivas."""
    guia_input = st.text_area("Checklist de Auditoria:", value=guia_padrao, height=200)

if "sumario_pronto" not in st.session_state:
    st.session_state.sumario_pronto = False
    st.session_state.texto_sumario = ""

if st.button("🚀 Gerar Sumário Executivo"):
    if file_uploaded:
        try:
            # Inicialização do LLM com a chave resolvida (prioridade .env)
            if modo_execucao == "API Key":
                if not api_key_final:
                    st.error("⚠️ Erve: Nenhuma API Key encontrada no .env ou no ecrã.")
                    st.stop()
                llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key_final, temperature=0.1)
            else:
                llm = ChatOllama(model=modelo_selecionado, base_url=f"http://{torre_ip}:11434", temperature=0.1)
            
            with st.spinner("A analisar hierarquia e extrair riscos..."):
                texto_cru = read_document(file_uploaded)
                st.session_state.texto_sumario = extrair_sumario_executivo(texto_cru, guia_input, llm)
                st.session_state.sumario_pronto = True
        except Exception as e:
            st.error(f"Erro Crítico: {e}")
    else:
        st.warning("⚠️ Carrega um ficheiro primeiro.")

# --- 5. EXIBIÇÃO DOS RESULTADOS ---
if st.session_state.sumario_pronto:
    st.markdown("---")
    st.header("📋 Sumário Técnico por Hierarquia")
    
    # Exibição do texto gerado pela IA
    st.markdown(st.session_state.texto_sumario)
    
    st.markdown("---")
    st.download_button("📥 Descarregar Sumário (TXT)", data=st.session_state.texto_sumario, file_name="Sumario_Executivo_BlocoAI.txt")
    
    if st.button("🔄 Nova Análise"):
        st.session_state.sumario_pronto = False
        st.rerun()