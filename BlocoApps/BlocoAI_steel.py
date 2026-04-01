import streamlit as st
import pandas as pd
import time
import pdfplumber 
import os
import io 
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
    st.sidebar.caption("Modelo Ativo: gpt-oss-120b")
    api_key_default = os.getenv("GROQ_API_KEY", "")
    api_key = st.sidebar.text_input("🔑 API Key", value="", type="password")
else:
    torre_ip = st.sidebar.text_input("🌐 IP da Torre", value="100.105.95.121")
    modelo_selecionado = st.sidebar.selectbox("🧠 LLM", ["qwen3.5:9b", "llama3.2:3b"])


# --- 2. LEITURA DE DADOS COM RASTREABILIDADE ---
def read_excel_ultra_clean(uploaded_file) -> str:
    xls = pd.ExcelFile(uploaded_file)
    text_lines = []
    for sheet in xls.sheet_names:
        df = xls.parse(sheet).astype(str)
        for idx, row in df.iterrows():
            valores = [v.strip() for v in row if v.strip().lower() not in ['nan', 'none', '0.0', '0', '']]
            if len(valores) > 1:  
                linha_texto = f"[Linha: {idx+2}] " + " | ".join(valores)
                text_lines.append(linha_texto)
    return "\n".join(list(dict.fromkeys(text_lines)))

def read_pdf_ultra_clean(uploaded_file) -> str:
    text_lines = []
    with pdfplumber.open(uploaded_file) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text(layout=True) 
            if text:
                linhas = [f"[Pág: {i+1}] {linha.strip()}" for linha in text.split('\n') if linha.strip()]
                text_lines.extend(linhas)
    return "\n".join(text_lines) 


# --- 3. MOTOR DE EXTRAÇÃO DE TEXTO RICO ---
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
    
    notas_recolhidas = [] 
    
    st.markdown("### 📡 Monitor de Extração")
    progresso_bar = st.progress(0)
    status_text = st.empty()
    caixa_resultados = st.empty()

    mensagem_sistema = SystemMessage(
        content="""You are a Senior Structural Steel Engineer.

Your task is to exhaustively extract ALL elements related to steel, secondary steel, fixings, gratings, and fire protection.

CONSOLIDATION & FORMATTING RULE (CRITICAL):
- Group identical items within the block by combining their reference tags.
- DO NOT ignore items just because they lack detailed technical specifications. If it's a steel/metal item or fire protection, extract it.
- You MUST output exactly 3 segments separated by the pipe symbol (|).

Output format:
- Format: Source Reference | Item | Detailed Specification
- 'Source Reference' MUST be the exact [Linha: Y] or [Pág: X] tag.
- No headers, no conversational text."""
    )

    for i, chunk in enumerate(chunks):
        bloco_num = i + 1
        status_text.text(f"🔍 A processar bloco {bloco_num} de {len(chunks)}...")
        progresso_bar.progress(bloco_num / len(chunks))
        
        with st.expander(f"👁️ Ver Texto Cru do Bloco {bloco_num}", expanded=False):
            st.text(chunk)

        prompt_bloco = f"""Lê o BOQ / Caderno de Encargos (EN) e extrai os dados DE FORMA EXAUSTIVA.

Usa a MATRIZ DE AUDITORIA abaixo como a tua 'checklist' principal. Tudo o que encaixar nestas categorias tem de ser extraído:

### MATRIZ DE AUDITORIA (O que procurar):
{guia_texto}

Regras Críticas:
1. EXTRAI TUDO O QUE SEJA RELEVANTE À MATRIZ E A AÇO.
2. Se um elemento metálico ou proteção ao fogo estiver listado mas não tiver grau/norma, extrai a descrição original. Não omitas elementos!

Formato OBRIGATÓRIO (3 partes separadas por '|'):
Referência de Origem | Item Principal | Especificação ou Descrição Completa

EXCERTO DO DOCUMENTO:
{chunk}

RESULTADO:"""

        try:
            res = llm.invoke([mensagem_sistema, HumanMessage(content=prompt_bloco)])
            linhas_resposta = res.content.strip().split('\n')
            
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
                notas_recolhidas.append(f"--- DADOS DO BLOCO {bloco_num} ---\n{resposta_final}\n")
                caixa_resultados.text_area(f"Resultados (Até Bloco {bloco_num}):", value="\n".join(notas_recolhidas), height=400)
            
            if modo == "API Key" and i < len(chunks) - 1:
                st.toast("⏳ Pausa de 25s (Proteção de Limite de API)")
                time.sleep(25)
                
        except Exception as e:
            st.error(f"⚠️ Erro na API (Bloco {bloco_num}): {e}")
            if "429" in str(e): 
                st.warning("🚨 Limite atingido. Pausa de 60s...")
                time.sleep(60)
            
    return "\n".join(notas_recolhidas)


# --- 4. INTERFACE PRINCIPAL ---
st.title("🏗️ BlocoAI: Extrator de Excel & PDF")
st.markdown("Auditoria automática focada em Estruturas Metálicas com Rastreabilidade.")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Ficheiro de Orçamento")
    file_uploaded = st.file_uploader("Carrega o ficheiro do cliente", type=["xlsx", "xls", "pdf"])

with col2:
    st.subheader("2. Matriz de Auditoria")
    st.info("O modo 'Engenheiro de Aço (Texto Rico + Rastros)' está ativo.")
    guia_padrao = """1. CLASSE EXECUÇÃO: EXC2, EXC3, EXC4
2. MATERIAL DE BASE: Tipo/Grade de Aço (S235 a S460, JR/J0/J2), Normas.
3. PARAFUSOS / CHUMBADOUROS: Fixações, Holding down bolts, Métrica, Classe 8.8/10.9.
4. PROTEÇÃO ANTI CORROSIVA: Galvanização, Pintura, Microns.
5. PROTEÇÃO AO FOGO: Intumescente (R30, 1 Hr, 2 Hr), Fire boards.
6. SECONDARY STEEL: Escadas, Guarda-corpos (Handrails), Cat Ladders, Bollards.
7. COMPLEXO COBERTURA/FACHADA: Steel Decking, Painéis."""
    guia_input = st.text_area("Notas adicionais e Matriz:", value=guia_padrao, height=180)

# --- INICIALIZAR A MEMÓRIA DA APP ---
if "dados_prontos" not in st.session_state:
    st.session_state.dados_prontos = False
    st.session_state.notas_finais = ""
    st.session_state.df_tabela = None

if st.button("🚀 Iniciar Análise"):
    if file_uploaded:
        try:
            if modo_execucao == "API Key":
                if not api_key.strip():
                    st.error("⚠️ API Key em falta. Coloca-a na barra lateral.")
                    st.stop()
                # ERRO DE INDENTAÇÃO CORRIGIDO AQUI:
                llm = ChatGroq(model_name="openai/gpt-oss-120b", api_key=api_key, temperature=0.1)
            else:
                base_url_ollama = "http://127.0.0.1:11434" if modo_execucao == "Local" else f"http://{torre_ip}:11434"
                llm = ChatOllama(model=modelo_selecionado, base_url=base_url_ollama, temperature=0.1, num_ctx=16384)
            
            with st.spinner("A processar ficheiro e a etiquetar linhas..."):
                if file_uploaded.name.lower().endswith('.pdf'):
                    texto_completo = read_pdf_ultra_clean(file_uploaded)
                else:
                    texto_completo = read_excel_ultra_clean(file_uploaded)

            notas_finais = processar_por_chunks_exaustivo(texto_completo, guia_input, llm, modo_execucao)

            if len(notas_finais.strip()) < 10:
                st.warning("⚠️ Sem dados extraídos.")
            else:
                linhas_brutas = notas_finais.strip().split('\n')
                dados_agrupados = {} 
                
                for linha in linhas_brutas:
                    linha = linha.strip()
                    if "|" in linha and not linha.startswith("---"): 
                        partes = [p.strip() for p in linha.split("|", 2)] 
                        
                        if len(partes) == 3:
                            ref, item, spec = partes
                        elif len(partes) == 2:
                            ref, item, spec = "Sem Ref", partes[0], partes[1]
                        else:
                            continue
                            
                        chave = spec.lower() 
                        
                        if chave in dados_agrupados:
                            if ref != "Sem Ref" and ref not in dados_agrupados[chave]["Referência (Excel/PDF)"]:
                                dados_agrupados[chave]["Referência (Excel/PDF)"] += f"; {ref}"
                        else:
                            dados_agrupados[chave] = {
                                "Referência (Excel/PDF)": ref,
                                "Elemento de Aço": item,
                                "Especificação Completa (BOQ)": spec
                            }
                
                if dados_agrupados:
                    st.session_state.df_tabela = pd.DataFrame(list(dados_agrupados.values()))
                    st.session_state.notas_finais = notas_finais
                    st.session_state.dados_prontos = True
                else:
                    st.warning("Não foi possível estruturar os dados para a tabela.")

        except Exception as e:
            st.error(f"Erro: {e}")
    else:
        st.warning("⚠️ Carrega um ficheiro primeiro.")

# --- MOSTRAR RESULTADOS ---
if st.session_state.dados_prontos:
    st.markdown("---")
    st.subheader("📄 Relatório Técnico Final")
    
    df_tabela = st.session_state.df_tabela
    notas_finais = st.session_state.notas_finais
    
    st.success(f"Extração concluída! Encontrados {len(df_tabela)} itens únicos com rastreabilidade.")
    st.dataframe(df_tabela, use_container_width=True)
    
    col_btn1, col_btn2 = st.columns(2)
    cabecalho = "Origem | Elemento de Aço | Especificação Técnica Completa\n"
    texto_final = cabecalho + notas_finais
    col_btn1.download_button("📝 Descarregar Dados (TXT)", data=texto_final, file_name="Extracao_Aco.txt")
    
    csv_buffer = io.BytesIO()
    df_tabela.to_csv(csv_buffer, index=False, sep=";", encoding="utf-8-sig")
    col_btn2.download_button("📊 Descarregar Tabela (CSV)", data=csv_buffer.getvalue(), file_name="Orcamento_Aco.csv", mime="text/csv")