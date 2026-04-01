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

# --- 0. CARREGAR AMBIENTE ---
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
            if chave.startswith("export "): chave = chave[len("export "):].strip()
            valor = valor.strip().strip('"').strip("'")
            if chave: os.environ[chave] = valor
        return

carregar_env_local()

# --- 1. CONFIGURAÇÃO DA INTERFACE ---
st.set_page_config(page_title="BlocoAI - Auditoria Hierárquica", layout="wide", page_icon="🏗️")

st.sidebar.title("Configurações")
modo_execucao = st.sidebar.radio("Ligação", ["API Key", "Local"], index=0)
api_key_env = os.getenv("CHATGPT_API_KEY", "")

if modo_execucao == "API Key":
    api_key_input = st.sidebar.text_input("🔑 API Key (Overwrite)", value="", type="password")
    api_key_final = api_key_input.strip() if api_key_input.strip() else api_key_env
else:
    torre_ip = st.sidebar.text_input("🌐 IP da Torre", value="100.105.95.121")
    modelo_selecionado = st.sidebar.selectbox("🧠 LLM", ["qwen3.5:9b", "llama3.2:3b"])

# --- 2. LEITURA ---
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

# --- 3. MOTORES DE INTELIGÊNCIA ---

# --- ATUALIZAÇÃO DO MOTOR DE SUMARIZAÇÃO (Etapa 1) ---

# --- 3. MOTOR DE SUMARIZAÇÃO (Ajustado para Nomes Reais) ---

# --- 3. MOTOR DE EXTRAÇÃO DE "SUMO" TÉCNICO (Fase 1) ---

# --- 3. MOTOR DE EXTRAÇÃO (Fase 1: Coleta do "Sumo" Técnico) ---

def extrair_sumario_parcial(texto_integral: str, guia_texto: str, llm):
    tamanho_max_chunk = 15000 
    chunks = [texto_integral[i:i + tamanho_max_chunk] for i in range(0, len(texto_integral), tamanho_max_chunk)]
    resumos_finais = []
    st.markdown("### 📡 Fase 1: Mapeando Identidade Técnica e Zonas...")
    progresso_bar = st.progress(0)

    # O segredo aqui é pedir para LISTAR em vez de RESUMIR
    mensagem_sistema = SystemMessage(
        content=f"""You are a Technical Data Hunter for a Construction Budgeting team.
        
        GOAL: Extract all technical details for each item, keeping their real context.
        
        1. HEADERS: Identify the real Phase (PH1, etc.) and Zone names (FSA, DCH, EYD).
        2. TECHNICAL DATA (The Sumo): For each item, list:
           - Material Grades: (e.g., S355, C20/25, C30/37).
           - Execution/Standard: (e.g., EXC2, EN 1090, BS 5911).
           - Protection: (e.g., Sa2.5, Galvanized, R60, Microns).
           - Scope Detail: (e.g., 'Includes excavations', 'BIM coordination', 'Connection design').
        3. NO QUANTITIES: Ignore numbers like 711.00, 50.5, etc.
        4. NO DATA LOSS: If a grade like 'C20/25' is in the text, you MUST record it.
        """
    )

    for i, chunk in enumerate(chunks):
        progresso_bar.progress((i + 1) / len(chunks))
        try:
            # Pedimos para ele ser um "Catalogador"
            prompt_auditoria = f"List all technical specifications and their real Phase/Zone names found here:\n\n{chunk}"
            res = llm.invoke([mensagem_sistema, HumanMessage(content=prompt_auditoria)])
            resumos_finais.append(res.content)
            time.sleep(0.5)
        except Exception as e: st.error(f"Erro no bloco {i}: {e}")
    return "\n\n".join(resumos_finais)

# --- 4. CONSOLIDAÇÃO (Fase 2: Auditoria e Árvore Final) ---

def gerar_consolidacao_hierarquica(resumos_acumulados, guia_input, llm):
    st.markdown("### 🔍 Fase 2: Polimento Hierárquico e Auditoria Técnica...")
    
    mensagem_sistema = SystemMessage(
        content=f"""You are a Senior Structural Estimator. Your goal is to produce a SHARP Technical Report.
        
        REFINEMENT RULES:
        1. LOCAL CONTEXT ONLY: Only list materials (S355, C20/25) that actually appear in that specific Zone. Do not copy materials from one zone to another (e.g., S355 is for Steel, C20/25 is for Drainage).
        2. STANDARDS VS CODES: Distinguish between technical standards (EN, BS, ISO) and project codes (CSA, PH1). CSA is a PROJECT ID, not a standard.
        3. THE SUMO: Keep the scope inclusions (e.g., "Includes excavations", "Includes fixings").
        4. INCONSISTENCIES: Flag if the same zone has conflicting data (e.g., PH1-DCH says S355 and PH2-DCH says S275).
        
        STRUCTURE:
        Project: [Real ID: CSA]
        --> Phase: [Real Name]
           --> Zone: [Real Name]
              ---> TECHNICAL PROFILE: [Grades, Execution Classes, Standards]
              ---> SCOPE ALERTS: [The "Sumo": Inclusions, exclusions, risks]
              ---> INCONSISTENCIES: [Specific conflicts or 'None']
        """
    )
    
    try:
        # Forçamos a IA a ser crítica com o que recebeu da Fase 1
        res = llm.invoke([mensagem_sistema, HumanMessage(content=f"Review and polish this data into the final tree:\n\n{resumos_acumulados}")])
        return res.content
    except Exception as e: return f"Erro: {e}"

# --- 4. INTERFACE PRINCIPAL ---
st.title("🏗️ BlocoAI: Auditoria Técnica Hierárquica")
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Ficheiro")
    file_uploaded = st.file_uploader("BOQ / Caderno de Encargos", type=["xlsx", "xls", "pdf"])

with col2:
    st.subheader("2. Matriz de Auditoria Evoluída")
    guia_padrao = """1. ÂMBITO: Fabrico, Montagem, Engenharia de Ligações.
2. HIERARQUIA: Fases (PH1-3), Zonas (CSA, FSA, DCH).
3. MATERIAIS: Aço (S355/S275), EXC2-4, Perfis.
4. PROTEÇÕES: Pintura (Microns), Fogo (R60/120), Sa2.5.
5. RISCOS: Design Responsibility, Furos MEP, Prevalência de Specs.
6. SUSTENTABILIDADE: Conteúdo Reciclado, EPD, LEED/BREEAM.
7. INCONSISTÊNCIAS: Comparação de dados contraditórios entre linhas/áreas."""
    guia_input = st.text_area("Checklist de Auditoria:", value=guia_padrao, height=220)

if "relatorio_final" not in st.session_state:
    st.session_state.relatorio_final = ""
    st.session_state.processado = False

if st.button("🚀 Gerar Relatório Hierárquico"):
    if file_uploaded:
        try:
            if modo_execucao == "API Key":
                if not api_key_final: st.error("API Key em falta."); st.stop()
                llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key_final, temperature=0.1)
            else:
                llm = ChatOllama(model=modelo_selecionado, base_url=f"http://{torre_ip}:11434", temperature=0.1)
            
            with st.spinner("Analisando e Auditando..."):
                texto_cru = read_document(file_uploaded)
                resumos = extrair_sumario_parcial(texto_cru, guia_input, llm)
                st.session_state.relatorio_final = gerar_consolidacao_hierarquica(resumos, guia_input, llm)
                st.session_state.processado = True
        except Exception as e: st.error(f"Erro Crítico: {e}")
    else: st.warning("Carrega um ficheiro primeiro.")

# --- 5. EXIBIÇÃO ---
if st.session_state.processado:
    st.markdown("---")
    st.header("📋 Relatório de Auditoria Master")
    st.markdown(st.session_state.relatorio_final)
    
    st.markdown("---")
    st.download_button("📥 Descarregar Auditoria (TXT)", 
                       data=st.session_state.relatorio_final, 
                       file_name="Auditoria_Hierarquica_BlocoAI.txt")