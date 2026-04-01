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
import re

def carregar_env_local():
    base_dir = Path(__file__).resolve().parent
    candidatos = [base_dir / ".env", base_dir.parent / ".env"]
    for env_path in candidatos:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            linha = line.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            chave = chave.strip()
            if chave.startswith("export "):
                chave = chave[len("export "):].strip()
            valor = valor.strip().strip('"').strip("'")
            if chave:
                if not os.getenv(chave):
                    os.environ[chave] = valor
        return

carregar_env_local()

# --- 1. CONFIGURAÇÃO DA INTERFACE ---
st.set_page_config(page_title="BlocoAI - Orçamentação", layout="wide", page_icon="🏗️")

st.sidebar.image("https://img.icons8.com/fluency/96/structural.png", width=80)
st.sidebar.title("Configurações do Servidor")

modo_execucao = st.sidebar.radio("Ligação", ["Remoto", "Local", "API Key"], index=0)

if modo_execucao == "API Key":
    st.sidebar.caption("Modelo Ativo: gpt-4o-mini")
    api_key_default = os.getenv("CHATGPT_API_KEY", "")
    api_key_input = st.sidebar.text_input("🔑 API Key", value="", type="password")
    api_key = api_key_input.strip() or api_key_default.strip()
else:
    torre_ip = st.sidebar.text_input("🌐 IP da Torre", value="100.105.95.121")
    modelo_selecionado = st.sidebar.selectbox("🧠 LLM", ["qwen3.5:9b", "llama3.2:3b"])

# --- 2. LEITURA DE DADOS ---
def read_excel_ultra_clean(uploaded_file) -> str:
    xls = pd.ExcelFile(uploaded_file)
    text_lines = []
    for sheet in xls.sheet_names:
        df = xls.parse(sheet).astype(str)
        for idx, row in df.iterrows():
            valores = [v.strip() for v in row if v.strip().lower() not in ['nan', 'none', '0.0', '0', '']]
            if len(valores) > 1:  
                text_lines.append(f"[Linha: {idx+2}] " + " | ".join(valores))
    return "\n".join(list(dict.fromkeys(text_lines)))

def read_pdf_ultra_clean(uploaded_file) -> str:
    text_lines = []
    with pdfplumber.open(uploaded_file) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text(layout=True) 
            if text:
                text_lines.extend([f"[Pág: {i+1}] {l.strip()}" for l in text.split('\n') if l.strip()])
    return "\n".join(text_lines) 

# --- 3. MOTOR DE EXTRAÇÃO HIERÁRQUICA ---
def processar_por_chunks_exaustivo(texto_integral: str, guia_texto: str, llm, modo: str):
    tamanho_max_chunk = 15000 
    linhas_texto = texto_integral.split('\n')
    chunks = []
    chunk_atual = ""
    for linha in linhas_texto:
        if len(chunk_atual) + len(linha) + 1 > tamanho_max_chunk:
            chunks.append(chunk_atual.strip()); chunk_atual = linha + "\n"
        else: chunk_atual += linha + "\n"
    if chunk_atual.strip(): chunks.append(chunk_atual.strip())
    
    notas_recolhidas = [] 
    st.markdown("### 📡 Monitor de Extração Hierárquica")
    progresso_bar = st.progress(0); status_text = st.empty(); caixa_resultados = st.empty()

    # MENSAGEM DE SISTEMA AJUSTADA: FASE -> ZONA
    mensagem_sistema = SystemMessage(
        content="""You are a Senior Structural Steel Engineer. 
Extract technical data respecting this strict hierarchy: PHASE first, then ZONE.

OUTPUT FORMAT (Exactly 5 segments separated by '|'):
Source Reference | Phase-Zone | Category | Item | Technical Detail

HIERARCHY RULES:
1. PHASE: PH1, PH2, PH3, etc.
2. ZONE: CSA, EYD, MYD, DCH, FSA, etc.
3. If a Phase is found but no Zone, use 'Phase - General'.
4. 'Technical Detail' must include Grades (S355), Standards, and Treatments. NO math.

Example: [Linha: 10] | PH1 - CSA | Structural Steel | Beam | S355, EXC2, Galvanized"""
    )

    for i, chunk in enumerate(chunks):
        bloco_num = i + 1
        status_text.text(f"🔍 Analisando Fase e Zona: Bloco {bloco_num} de {len(chunks)}...")
        progresso_bar.progress(bloco_num / len(chunks))
        
        prompt_bloco = f"""Extrai os dados de aço. Prioriza identificar a FASE e depois a ZONA.
Matriz de Auditoria:
{guia_texto}

Regras:
1. Identifica obrigatoriamente a Fase (ex: PH1) e a Zona (ex: CSA).
2. Formato: Referência | Fase-Zona | Categoria | Item | Detalhe Técnico

TEXTO:
{chunk}

RESULTADO:"""

        try:
            res = llm.invoke([mensagem_sistema, HumanMessage(content=prompt_bloco)])
            linhas = [l.strip() for l in res.content.strip().split('\n') if "|" in l]
            if linhas:
                bloco_str = "\n".join(linhas)
                notas_recolhidas.append(f"--- BLOCO {bloco_num} ---\n{bloco_str}")
                caixa_resultados.text_area("Live Output:", value="\n".join(notas_recolhidas), height=300)
            if modo == "API Key": time.sleep(1) # OpenAI é mais rápida, 1s basta
        except Exception as e: st.error(f"Erro: {e}")
            
    return "\n".join(notas_recolhidas)

# --- 4. INTERFACE E PROCESSAMENTO FINAL ---
st.title("🏗️ BlocoAI: Extrator Hierárquico")
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Ficheiro de Orçamento")
    file_uploaded = st.file_uploader("Carrega o ficheiro (Excel ou PDF)", type=["xlsx", "xls", "pdf"])

with col2:
    st.subheader("2. Definição de Hierarquia")
    guia_padrao = "FASES: PH1, PH2, PH3\nZONAS: CSA, EYD, MYD, DCH, FSA\nCATEGORIAS: Proteções, Fogo, Decking, Estrutura"
    guia_input = st.text_area("Bússola para a IA:", value=guia_padrao, height=150)

# Inicializar estados de memória
if "dados_prontos" not in st.session_state:
    st.session_state.dados_prontos = False
    st.session_state.df_tabela = None

if st.button("🚀 Iniciar Análise"):
    if file_uploaded:
        try:
            # Configuração do Modelo (OpenAI ou Ollama)
            if modo_execucao == "API Key":
                llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0.1)
            else:
                llm = ChatOllama(model=modelo_selecionado, base_url=f"http://{torre_ip}:11434", temperature=0.1)
            
            # 1. Leitura do ficheiro
            with st.spinner("A ler documento..."):
                texto = read_pdf_ultra_clean(file_uploaded) if file_uploaded.name.endswith('.pdf') else read_excel_ultra_clean(file_uploaded)
            
            # 2. Extração via IA
            notas_finais = processar_por_chunks_exaustivo(texto, guia_input, llm, modo_execucao)

            # 3. Transformação em DataFrame com separação de Fase/Zona
            linhas = [l for l in notas_finais.split('\n') if "|" in l and not l.startswith("---")]
            dados = []
            for l in linhas:
                p = [x.strip() for x in l.split("|", 4)]
                if len(p) == 5:
                    fase_zona_raw = p[1]
                    fase = fase_zona_raw.split('-')[0].strip() if '-' in fase_zona_raw else fase_zona_raw
                    zona = fase_zona_raw.split('-')[1].strip() if '-' in fase_zona_raw else "Geral"
                    
                    dados.append({
                        "Origem": p[0],
                        "Fase": fase,
                        "Zona": zona,
                        "Categoria": p[2],
                        "Elemento": p[3],
                        "Especificação": p[4]
                    })
            
            if dados:
                st.session_state.df_tabela = pd.DataFrame(dados)
                st.session_state.dados_prontos = True
            else:
                st.warning("A IA não detetou elementos válidos. Tenta ajustar a Matriz.")

        except Exception as e:
            st.error(f"Erro no processamento: {e}")
    else:
        st.warning("⚠️ Por favor, carrega um ficheiro primeiro.")

# --- 5. VISUALIZAÇÃO HIERÁRQUICA (Phase -> Zone -> Details) ---
if st.session_state.dados_prontos:
    st.markdown("---")
    st.header("📄 Relatório Estruturado de Auditoria")
    
    df = st.session_state.df_tabela
    fases = sorted(df['Fase'].unique())

    for fase in fases:
        st.markdown(f"### 🏗️ Fase: {fase}")
        df_fase = df[df['Fase'] == fase]
        
        zonas = sorted(df_fase['Zona'].unique())
        for zona in zonas:
            # Usamos expander para não ocupar demasiado espaço vertical
            with st.expander(f"📍 Zona: {zona}", expanded=True):
                df_zona = df_fase[df_fase['Zona'] == zona]
                # Mostramos os detalhes ranhura a ranhura
                st.table(df_zona[["Elemento", "Categoria", "Especificação", "Origem"]])

    st.markdown("---")
    # Botão de Download do CSV consolidado
    csv_buffer = io.BytesIO()
    df.to_csv(csv_buffer, index=False, sep=";", encoding="utf-8-sig")
    st.download_button(
        "📊 Descarregar Tabela Completa (CSV)", 
        data=csv_buffer.getvalue(), 
        file_name="Orcamento_Hierarquico.csv", 
        mime="text/csv"
    )