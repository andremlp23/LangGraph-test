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

def extrair_sumario_parcial(texto_integral: str, guia_texto: str, llm):
    tamanho_max_chunk = 15000 
    chunks = [texto_integral[i:i + tamanho_max_chunk] for i in range(0, len(texto_integral), tamanho_max_chunk)]
    resumos_finais = []
    st.markdown("### 📡 Fase 1: Auditoria Técnica (Filtro de Specs)...")
    progresso_bar = st.progress(0)

    mensagem_sistema = SystemMessage(
        content=f"""You are a Technical Auditor for Structural Steel. 
        Your task is to extract only the TECHNICAL DNA of the items.
        
        CRITICAL DISTINCTION:
        1. DELETE Commercial Quantities: e.g., 711.00, 50.5, 1.200, 22. (Numbers alone).
        2. KEEP Technical Specs: e.g., S355, S275, EXC2, EXC3, R60, R120, 2Hr, 150microns, Sa2.5, EN 1090.
        
        INSTRUCTIONS:
        - Scan each line for the keywords in the Audit Matrix: {guia_texto}.
        - If a line says 'Steel Grade S355', the spec is 'S355'.
        - If you see 'Intumescent 2hr', the spec is '2hr'.
        - NEVER write 'Not specified' if there is technical text nearby. Use the original technical description.
        """
    )

    for i, chunk in enumerate(chunks):
        progresso_bar.progress((i + 1) / len(chunks))
        try:
            # Forçamos a IA a não ser preguiçosa
            prompt_auditoria = f"Identify all technical specifications (Grades, Classes, Fire, Paint) in this text. IGNORE quantities. TEXT:\n\n{chunk}"
            res = llm.invoke([mensagem_sistema, HumanMessage(content=prompt_auditoria)])
            resumos_finais.append(res.content)
            time.sleep(0.5)
        except Exception as e: st.error(f"Erro no bloco {i}: {e}")
    return "\n\n".join(resumos_finais)

# --- ATUALIZAÇÃO DA CONSOLIDAÇÃO HIERÁRQUICA (Etapa 2) ---

def gerar_consolidacao_hierarquica(resumos_acumulados, guia_input, llm):
    st.markdown("### 🔍 Fase 2: Consolidando Árvore de Decisão...")
    
    mensagem_sistema = SystemMessage(
        content=f"""You are a Chief Auditor. Create a nested hierarchical report.
        
        REPORT STRUCTURE:
        Project > Phase > Zone
        --> TECHNICAL PROFILE: Summarize the specs (Grades, Classes, Ratings, Painting).
        --> SCOPE & RISKS: (e.g., BIM, Design Responsibility, MEP coordination).
        --> INCONSISTENCIES: Flag only if technical specs conflict (e.g., S355 vs S275).
        
        MANDATORY:
        - If the previous blocks found 'S355' or 'EXC2', they MUST appear here.
        - Do not summarize so much that you lose the specific grades.
        """
    )
    
    try:
        res = llm.invoke([mensagem_sistema, HumanMessage(content=resumos_acumulados)])
        return res.content
    except Exception as e: return f"Erro na consolidação: {e}"

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