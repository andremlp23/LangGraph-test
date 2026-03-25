import streamlit as st
import pandas as pd
import time
import pdfplumber 
import os
from pathlib import Path
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
import re


def carregar_env_local():
    """Carrega variáveis do .env da pasta do app ou da raiz do projeto."""
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
    api_key = st.sidebar.text_input("API Key", value=api_key_default, type="password")
else:
    torre_ip = st.sidebar.text_input("IP da Torre Ollama", value="100.105.95.121")
    modelo_selecionado = st.sidebar.selectbox("LLM", ["qwen3.5:9b", "llama3.2:3b"])


# --- 2. LEITURA INTELIGENTE DE EXCEL E PDF ---
def read_excel_ultra_clean(uploaded_file) -> str:
    """Lê o Excel, junta as colunas na mesma linha e remove lixo."""
    xls = pd.ExcelFile(uploaded_file)
    text_lines = []
    
    for sheet in xls.sheet_names:
        df = xls.parse(sheet).astype(str)
        
        for _, row in df.iterrows():
            valores = [v.strip() for v in row if v.strip().lower() not in ['nan', 'none', '0.0', '0', '']]
            if len(valores) > 1:  
                linha_texto = " | ".join(valores)
                text_lines.append(linha_texto)
                
    return "\n".join(list(dict.fromkeys(text_lines)))

def read_pdf_ultra_clean(uploaded_file) -> str:
    """Lê o PDF mantendo o layout das tabelas."""
    text_lines = []
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True) 
            if text:
                linhas = [linha.strip() for linha in text.split('\n') if linha.strip()]
                text_lines.extend(linhas)
                
    return "\n".join(text_lines) 

# --- 3. MOTOR DE EXTRAÇÃO EM TEMPO REAL ---
def processar_por_chunks_exaustivo(texto_integral: str, guia_texto: str, llm, modo: str):
    
    # Se for API, cortamos mais pequeno para não exceder TPM (Tokens Per Minute) da versão grátis
    tamanho_chunk = 4000 if modo == "API Key" else 15000 
    chunks = [texto_integral[i:i + tamanho_chunk] for i in range(0, len(texto_integral), tamanho_chunk)]
    
    notas_recolhidas = []
    
    st.markdown("### 📡 Monitor de Extração: Foco em Aço (Steel)")
    progresso_bar = st.progress(0)
    status_text = st.empty()
    caixa_resultados = st.empty()

    # MENSAGEM DE SISTEMA COM REGRA DE CONSOLIDAÇÃO (A IA a "Pensar")
    mensagem_sistema = SystemMessage(
        content="""You are a Senior Structural Steel Engineer.

Your task is to extract all relevant technical specifications related strictly to steel elements.

🧠 CONSOLIDATION & DEDUPLICATION RULE (CRITICAL):
- Before generating your output, mentally review the elements you found in the text.
- If you find multiple items with the EXACT SAME technical specifications, DO NOT repeat them.
- Group and consolidate them into a SINGLE line. 
- Example: If the text mentions "Steel Column S355" 10 times, you output it only ONCE.

Output format:
- One item per line
- Format: Item | Detailed Steel Specification
- No headers, no conversational text

Never infer or invent data."""
    )

    for i, chunk in enumerate(chunks):
        status_text.text(f"🔍 Extração Especializada: Bloco {i+1} de {len(chunks)}...")
        progresso_bar.progress((i + 1) / len(chunks))
        
        with st.expander(f"👁️ Ver Texto Cru do Bloco {i+1}", expanded=False):
            st.text(chunk)

        # O TEU PROMPT EXATO RESTAURADO
        prompt_bloco = f"""Lê o BOQ / Caderno de Encargos (EN) e aplica as regras definidas no system prompt.

Foca-te EXCLUSIVAMENTE em elementos de aço definidos como:
- Structural steel (beams, columns, frames, trusses)
- Secondary steel (brackets, supports, connections)
- Steel decking and steel-based cladding ONLY if explicitly metallic
- Fixings ONLY if specified as steel components
- Reinforcements ONLY if explicitly described as steel elements (e.g., steel plates, stiffeners)

Ignora:
- Materiais não metálicos ou não aço (betão, madeira, alumínio, etc.)

Extração:
- Extrai o máximo detalhe técnico relevante:
  - Normas (EN, BS, NSSS, etc.)
  - Graus de aço (S235, S355, JR, J0)
  - Classes de execução (EXC2, EXC3)
  - Tipos de perfil
  - Espessuras (ex: 10mm — manter se fizer parte da especificação)
  - Tratamentos (galvanização, pintura, microns)
  - Proteção ao fogo (R60, R120, intumescente)

Regras críticas:
1. NÃO extrair quantidades isoladas (ex: 10 unidades, 500 kg)
2. MANTER valores que fazem parte da especificação técnica (ex: 1.2mm, Class 8.8)
3. NÃO inventar dados

Formato:
- Uma linha por item
- Formato: Item | Especificação Técnica Completa
- Sem cabeçalhos ou texto extra

Edge cases:
- Se houver referência a aço sem detalhe técnico:
  Steel Element | Mentioned without technical specification
- Se não houver aço:
  SEM AÇO NESTE BLOCO

### EXCERTO DO DOCUMENTO:
{chunk}

### RESULTADO:"""
        
        try:
            res = llm.invoke([mensagem_sistema, HumanMessage(content=prompt_bloco)])
            linhas_resposta = res.content.strip().split('\n')
            
            # FILTRO ANTI-SPAM PYTHON (Segurança de última linha)
            linhas_limpas = []
            linhas_vistas = set()
            for linha in linhas_resposta:
                linha = linha.strip()
                if len(linha) > 5 and "|" in linha:
                    if linha not in linhas_vistas:
                        linhas_vistas.add(linha)
                        linhas_limpas.append(linha)
            
            resposta_final = "\n".join(linhas_limpas)
            
            if resposta_final:
                notas_recolhidas.append(f"--- DADOS DO BLOCO {i+1} ---\n{resposta_final}\n")
                
                texto_acumulado = "\n".join(notas_recolhidas)
                caixa_resultados.text_area(
                    f"Resultados Acumulados (Até Bloco {i+1}):", 
                    value=texto_acumulado, 
                    height=400
                )
            
            # TRAVÃO ANTI-RATE LIMIT DA GROQ
            if modo == "API Key" and i < len(chunks) - 1:
                st.toast("⏳ A respeitar os limites da API Groq. Pausa de 25 segundos...")
                time.sleep(25)
                
        except Exception as e:
            notas_recolhidas.append(f"⚠️ Erro no bloco {i+1}: {e}")
            if "429" in str(e): 
                st.warning("🚨 Limite da Groq atingido. A tentar recuperar em 60 segundos...")
                time.sleep(60)
            
    return "\n".join(notas_recolhidas)


# --- 4. INTERFACE PRINCIPAL ---
st.title("🏗️ BlocoAI: Extrator de Excel & PDF")
st.markdown("Auditoria automática focada em Estruturas Metálicas.")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Ficheiro de Orçamento")
    file_uploaded = st.file_uploader("Carrega o ficheiro do cliente", type=["xlsx", "xls", "pdf"])

with col2:
    st.subheader("2. Matriz de Auditoria")
    st.info("O modo 'Engenheiro de Aço' está ativo. A IA foca-se em S355, normas, tratamentos e afins.")
    guia_padrao = "MATRIZ DESATIVADA NESTE MODO (Regras no Prompt)."
    guia_input = st.text_area("Notas adicionais (Opcional):", value=guia_padrao, height=100)

if st.button("🚀 Iniciar Análise Completa"):
    if file_uploaded:
        try:
            if modo_execucao == "API Key":
                if not api_key.strip():
                    st.warning("⚠️ Introduz a API Key para usar o modo API.")
                    st.stop()

                llm = ChatGroq(
                    model_name="llama-3.3-70b-versatile",
                    api_key=api_key,
                    temperature=0.1
                )
            else:
                if modo_execucao == "Local":
                    base_url_ollama = "http://127.0.0.1:11434"
                else:
                    base_url_ollama = f"http://{torre_ip}:11434"

                llm = ChatOllama(model=modelo_selecionado, base_url=base_url_ollama, temperature=0.1, num_ctx=16384)
            
            with st.spinner("A processar ficheiro..."):
                if file_uploaded.name.lower().endswith('.pdf'):
                    texto_completo = read_pdf_ultra_clean(file_uploaded)
                    st.success("PDF processado! Layout de tabelas mantido.")
                else:
                    texto_completo = read_excel_ultra_clean(file_uploaded)
                    st.success("Excel processado! Texto comprimido.")

            notas_finais = processar_por_chunks_exaustivo(texto_completo, guia_input, llm, modo_execucao)
            
            st.markdown("---")
            st.subheader("📄 Relatório Técnico Final (Puro)")

            if len(notas_finais.strip()) < 10:
                st.warning("⚠️ A IA não extraiu dados de Aço após analisar todo o documento.")
            else:
                cabecalho = "Elemento de Aço | Especificação Técnica Completa\n"
                resultado_com_cabecalho = cabecalho + notas_finais
                st.download_button("📥 Descarregar Dados (TXT)", data=resultado_com_cabecalho, file_name="Extracao_Aco.txt")

        except Exception as e:
            st.error(f"Erro no sistema ou de ligação: {e}")
    else:
        st.warning("⚠️ Carrega primeiro o ficheiro na coluna da esquerda.")