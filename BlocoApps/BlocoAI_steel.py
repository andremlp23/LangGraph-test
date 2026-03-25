import streamlit as st
import pandas as pd
import time
import pdfplumber 
import os
import json # <-- ADICIONADO PARA O MODO JSON
from pathlib import Path
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
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
            valor = valor.strip().strip('"').strip("'")
            if chave:
                os.environ.setdefault(chave, valor)
        return

carregar_env_local()

# --- 1. CONFIGURAÇÃO DA INTERFACE ---
st.set_page_config(page_title="BlocoAI - Orçamentação", layout="wide", page_icon="🏗️")

st.sidebar.image("https://img.icons8.com/fluency/96/structural.png", width=80)
st.sidebar.title("Configurações do Servidor")

modo_execucao = st.sidebar.radio("Ligação", ["Remoto", "Local", "API Key"], index=0)

if modo_execucao == "API Key":
    st.sidebar.caption("Modelo fixo: Llama 3.3 70B (Groq)")
    api_key_default = os.getenv("GROQ_API_KEY", "")
    # DEVOLVIDA A CAIXA DE TEXTO (Para veres se a chave está realmente lá)
    api_key = st.sidebar.text_input("🔑 API Key", value="", type="password")
else:
    torre_ip = st.sidebar.text_input("🌐 IP da Torre", value="100.105.95.121")
    modelo_selecionado = st.sidebar.selectbox("🧠 LLM", ["qwen3.5:9b", "llama3.2:3b"])


# --- 2. LEITURA DE DADOS ---
def read_excel_ultra_clean(uploaded_file) -> str:
    xls = pd.ExcelFile(uploaded_file)
    text_lines = []
    for sheet in xls.sheet_names:
        df = xls.parse(sheet).astype(str)
        for _, row in df.iterrows():
            valores = [v.strip() for v in row if v.strip().lower() not in ['nan', 'none', '0.0', '0', '']]
            if len(valores) > 1:  
                text_lines.append(" | ".join(valores))
    return "\n".join(list(dict.fromkeys(text_lines)))

def read_pdf_ultra_clean(uploaded_file) -> str:
    text_lines = []
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True) 
            if text:
                linhas = [linha.strip() for linha in text.split('\n') if linha.strip()]
                text_lines.extend(linhas)
    return "\n".join(text_lines) 


# --- 3. MOTOR DE EXTRAÇÃO JSON ---
def processar_por_chunks_exaustivo(texto_integral: str, guia_texto: str, llm, modo: str):
    tamanho_max_chunk = 4000 if modo == "API Key" else 15000 
    
    linhas_texto = texto_integral.split('\n')
    chunks = []
    chunk_atual = ""
    for linha in linhas_texto:
        if len(chunk_atual) + len(linha) + 1 > tamanho_max_chunk:
            if chunk_atual:
                chunks.append(chunk_atual.strip())
                chunk_atual = linha + "\n"
            else:
                chunks.append(linha)
                chunk_atual = ""
        else:
            chunk_atual += linha + "\n"
    if chunk_atual.strip():
        chunks.append(chunk_atual.strip())
    
    todos_os_itens_json = [] # O nosso balde mestre de JSONs
    
    st.markdown("### 📡 Monitor de Extração JSON")
    progresso_bar = st.progress(0)
    status_text = st.empty()
    caixa_resultados = st.empty()

    mensagem_sistema = SystemMessage(
        content="""You are a Senior Structural Steel Engineer.
Your task is to extract technical specifications related to steel elements and output them STRICTLY AS A JSON ARRAY.

CONSOLIDATION RULE: Mentally review and group identical items before outputting.

OUTPUT FORMAT:
You must return ONLY a valid JSON array of objects. Do not write markdown, do not write explanations.
Use this EXACT JSON schema for each object:
{
  "source_block": [Insert Block Number Integer],
  "raw_item": "[Extracted item name]",
  "raw_spec": "[Full extracted specification text]",
  "category": "[e.g., STRUCTURAL_STEEL, SECONDARY_STEEL, FIXINGS, CLADDING]",
  "element": "[Standardized Element Name]",
  "properties": {
    "grade": "[e.g., 'S355', 'S235' or null]",
    "execution_class": "[e.g., 'EXC2', 'EXC3' or null]",
    "standard": "[e.g., 'NSSSBC 5th Edition', 'EN 1090' or null]"
  },
  "processes": ["[e.g., 'fabricated', 'erected']"],
  "coating": "[e.g., 'Galvanized', 'Painted' or null]",
  "fire_protection": "[e.g., 'Intumescent 60min', 'R120' or null]",
  "notes": "[Any other relevant detail or null]",
  "confidence": "[high, medium, low]"
}

If no steel is found in the block, return an empty array: []"""
    )

    for i, chunk in enumerate(chunks):
        bloco_num = i + 1
        status_text.text(f"🔍 A processar bloco {bloco_num} de {len(chunks)}...")
        progresso_bar.progress(bloco_num / len(chunks))
        
        with st.expander(f"👁️ Ver Texto Cru do Bloco {bloco_num}", expanded=False):
            st.text(chunk)

        # O SANDWICH PROMPT!
        prompt_bloco = f"""Extract the steel elements from the text below.
Apply the filtering and consolidation rules defined in your system prompt.

CRITICAL: Your response MUST be a valid JSON array of objects. 
Use this exact schema for each extracted item:
{{
  "source_block": {bloco_num},
  "raw_item": "...",
  "raw_spec": "...",
  "category": "...",
  "element": "...",
  "properties": {{
    "grade": "...",
    "execution_class": "...",
    "standard": "..."
  }},
  "processes": ["..."],
  "coating": "...",
  "fire_protection": "...",
  "notes": "...",
  "confidence": "..."
}}

If no steel is found, return []. Do not include markdown formatting or conversational text.

DOCUMENT EXCERPT (Block {bloco_num}):
{chunk}"""

        try:
            res = llm.invoke([mensagem_sistema, HumanMessage(content=prompt_bloco)])
            resposta_texto = res.content.strip()
            
            # Remove lixo markdown que a IA possa adicionar antes do JSON
            if resposta_texto.startswith("```json"):
                resposta_texto = resposta_texto.replace("```json", "").replace("```", "").strip()
            elif resposta_texto.startswith("```"):
                resposta_texto = resposta_texto.replace("```", "").strip()
                
            # Converter String em JSON Real e juntar à lista mestre
            try:
                dados_bloco = json.loads(resposta_texto)
                if isinstance(dados_bloco, list) and len(dados_bloco) > 0:
                    todos_os_itens_json.extend(dados_bloco)
            except json.JSONDecodeError:
                st.error(f"⚠️ O bloco {bloco_num} não devolveu um JSON válido. Ignorado.")
            
            # Mostra o JSON formatado no ecrã
            if todos_os_itens_json:
                caixa_resultados.json(todos_os_itens_json)
            
            if modo == "API Key" and i < len(chunks) - 1:
                st.toast("⏳ Pausa de 25s (Proteção de Limite de API)")
                time.sleep(25)
                
        except Exception as e:
            st.error(f"⚠️ Erro na API (Bloco {bloco_num}): {e}")
            if "429" in str(e): 
                st.warning("🚨 Limite atingido. Pausa de 60s...")
                time.sleep(60)
            
    return todos_os_itens_json


# --- 4. INTERFACE PRINCIPAL ---
st.title("🏗️ BlocoAI: Extrator de Excel & PDF")
st.markdown("Auditoria automática focada em Estruturas Metálicas.")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Ficheiro de Orçamento")
    file_uploaded = st.file_uploader("Carrega o ficheiro do cliente", type=["xlsx", "xls", "pdf"])

with col2:
    st.subheader("2. Matriz de Auditoria")
    st.info("O modo 'Engenheiro de Aço (JSON)' está ativo.")
    guia_padrao = "Extração estruturada em Base de Dados (JSON)."
    guia_input = st.text_area("Notas adicionais (Opcional):", value=guia_padrao, height=100)

if st.button("🚀 Iniciar Análise"):
    if file_uploaded:
        try:
            if modo_execucao == "API Key":
                if not api_key.strip():
                    st.error("⚠️ API Key em falta. Coloca-a na barra lateral.")
                    st.stop()
                llm = ChatGroq(model_name="llama-3.3-70b-versatile", api_key=api_key, temperature=0.1)
            else:
                base_url_ollama = "[http://127.0.0.1:11434](http://127.0.0.1:11434)" if modo_execucao == "Local" else f"http://{torre_ip}:11434"
                llm = ChatOllama(model=modelo_selecionado, base_url=base_url_ollama, temperature=0.1, num_ctx=16384)
            
            with st.spinner("A processar ficheiro..."):
                if file_uploaded.name.lower().endswith('.pdf'):
                    texto_completo = read_pdf_ultra_clean(file_uploaded)
                else:
                    texto_completo = read_excel_ultra_clean(file_uploaded)

            # A variável notas_finais agora é uma lista de dicionários!
            notas_finais = processar_por_chunks_exaustivo(texto_completo, guia_input, llm, modo_execucao)
            
            st.markdown("---")
            st.subheader("📄 Relatório Técnico Final")

            if not notas_finais:
                st.warning("⚠️ Sem dados extraídos.")
            else:
                # O BOTÃO DE DOWNLOAD AGORA DESCARREGA UM FICHEIRO .JSON
                json_string = json.dumps(notas_finais, indent=2, ensure_ascii=False)
                st.download_button("📥 Descarregar Dados (JSON)", data=json_string, file_name="Extracao_Aco.json", mime="application/json")

        except Exception as e:
            st.error(f"Erro: {e}")
    else:
        st.warning("⚠️ Carrega um ficheiro primeiro.")