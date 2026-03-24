import streamlit as st
import pdfplumber
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
import re

# --- 1. CONFIGURAÇÃO DA INTERFACE ---
st.set_page_config(page_title="BlocoAI - PDF Auditor", layout="wide", page_icon="📄")

st.sidebar.image("https://img.icons8.com/fluency/96/doc.png", width=80)
st.sidebar.title("Configurações do Servidor")

modo_execucao = st.sidebar.radio("Ligação", ["Remoto", "Local"], index=0)
torre_ip = st.sidebar.text_input("IP da Torre Ollama", value="100.105.95.121")
modelo_selecionado = st.sidebar.selectbox("Modelo de IA", ["qwen3.5:9b", "llama3.2:3b"])

st.sidebar.markdown("---")
st.sidebar.caption("Dica: O pdfplumber extrai tabelas e texto mantendo o layout.")

# --- 2. LEITURA E LIMPEZA DE PDF COM PDFPLUMBER ---
def read_pdf_ultra_clean(uploaded_file) -> str:
    """Lê o PDF mantendo o layout (crucial para especificações técnicas não se misturarem)."""
    text_content = []
    
    with pdfplumber.open(uploaded_file) as pdf:
        total_pages = len(pdf.pages)
        pdf_prog_bar = st.progress(0)
        
        for i, page in enumerate(pdf.pages):
            pdf_prog_bar.progress((i + 1) / total_pages, text=f"📖 A ler página {i+1} de {total_pages}...")
            
            # O layout=True é a magia que impede as palavras de se colarem umas às outras
            text = page.extract_text(layout=True)
            if text:
                # Limpa múltiplos espaços excessivos mas mantém a estrutura
                cleaned_text = re.sub(r' {3,}', '   ', text).strip()
                text_content.append(cleaned_text)
                
    return "\n".join(text_content)

# --- 3. MOTOR DE AUDITORIA DE PDF (MODO ESPONJA) ---
def processar_pdf_por_chunks(texto_integral: str, guia_texto: str, llm):
    tamanho_chunk = 15000 
    chunks = [texto_integral[i:i + tamanho_chunk] for i in range(0, len(texto_integral), tamanho_chunk)]
    
    notas_recolhidas = []
    
    st.markdown("### 📡 Monitor de Extração do PDF")
    progresso_bar = st.progress(0)
    status_text = st.empty()
    caixa_resultados = st.empty()

    # MENSAGEM DE SISTEMA (Modo "Aspirador de Dados")
    mensagem_sistema = SystemMessage(
        content=(
            "You are an expert Civil Engineering Auditor. Your task is to extract MAXIMUM technical information "
            "from the text. Capture all materials, norms, dimensions, execution rules, tolerances, and testing requirements. "
            "Do not summarize or omit technical details. Output as a clear pipe-separated list: Item | Detailed Specification. "
            "Never invent data. If there is no technical info, just say 'SEM DADOS'."
        )
    )

    for i, chunk in enumerate(chunks):
        status_text.text(f"🔍 Extração Máxima: Bloco {i+1} de {len(chunks)}...")
        progresso_bar.progress((i + 1) / len(chunks))
        
        with st.expander(f"👁️ Ver Texto Cru do PDF (Bloco {i+1})", expanded=False):
            st.text(chunk)

        # PROMPT DE EXTRAÇÃO LIVRE (Sem forçar matrizes)
        prompt_bloco = (
            "Atua como um Engenheiro Auditor. Lê o Caderno de Encargos (EN) e extrai ABSOLUTAMENTE TUDO o que for "
            "informação técnica relevante para fabrico, orçamentação e planeamento estrutural.\n\n"
            "Não limites a extração. Procura por: normas (EN, ISO, BS), graus de materiais, classes de execução (EXC), "
            "regras de soldadura, espessuras, ensaios não destrutivos (NDT), proteções anticorrosivas, e tolerâncias.\n\n"
            "FORMATO (Linha única por descoberta, separada por '|', SEM CABEÇALHOS):\n"
            "[Tópico / Material] | [Especificação Técnica Completa, Normas e Regras Extraídas do Texto]\n\n"
            "EXEMPLOS:\n"
            "Soldadura | Todos os soldadores devem ser qualificados segundo a norma EN 9606-1.\n"
            "Material Base | Perfis principais em aço S355 J2, ligações em S235 JR.\n"
            "Proteção Anticorrosiva | Sistema de pintura C4 High com 240 microns de espessura total.\n\n"
            f"### EXCERTO DO PDF:\n{chunk}\n\n"
            "### RESULTADO DA EXTRAÇÃO TÉCNICA (Apenas linhas reais):"
        )
        
        try:
            res = llm.invoke([mensagem_sistema, HumanMessage(content=prompt_bloco)])
            resposta = res.content.strip()
            
            # Se a IA encontrar dados, guardamos!
            if "SEM DADOS" not in resposta.upper() and len(resposta) > 15:
                notas_recolhidas.append(resposta)
            
            # --- ATUALIZAÇÃO EM TEMPO REAL CORRIGIDA ---
            texto_acumulado = "\n".join(notas_recolhidas)
            if texto_acumulado.strip():
                caixa_resultados.text_area(
                    f"Resultados Acumulados (Até Bloco {i+1}):", 
                    value=texto_acumulado, 
                    height=400
                )
                
        # --- EXCEPT RESTAURADO PARA NÃO CRASHAR A APP ---
        except Exception as e:
            notas_recolhidas.append(f"⚠️ Erro no bloco {i+1}: {e}")
            
    return "\n".join(notas_recolhidas)

# --- 4. INTERFACE PRINCIPAL ---
st.title("📄 BlocoAI - PDF Auditor")
st.markdown("Auditoria automática de conformidade em PDFs de Cadernos de Encargos.")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Ficheiro de Projeto (PDF)")
    file_pdf = st.file_uploader("Carrega o Caderno de Encargos", type=["pdf"])

with col2:
    # Como ativámos o modo "esponja", esta matriz é meramente visual agora, 
    # mas mantemos na interface para futuras versões.
    st.subheader("2. Foco de Auditoria Livre")
    st.info("O Modo 'Aspirador de Dados' está ativo. A IA vai extrair todas as regras e normas sem se limitar a uma matriz específica.")

if st.button("🚀 Iniciar Auditoria de Conformidade"):
    if file_pdf:
        try:
            if modo_execucao == "Local":
                base_url_ollama = "http://127.0.0.1:11434"
            else:
                base_url_ollama = f"http://{torre_ip}:11434"

            llm = ChatOllama(model=modelo_selecionado, base_url=base_url_ollama, temperature=0.1)
            
            with st.spinner("A ler PDF e a manter layout das tabelas..."):
                texto_completo = read_pdf_ultra_clean(file_pdf)
                st.success(f"PDF convertido! Total de caracteres lidos: {len(texto_completo)}.")
            
            relatorio_final = processar_pdf_por_chunks(texto_completo, "", llm) # Guia vazio pois não é usado
            
            st.markdown("---")
            st.subheader("📄 Relatório de Conformidade Técnica")

            if len(relatorio_final.strip()) < 10:
                st.warning("⚠️ Não encontrou conformidades ou o PDF é um documento digitalizado (imagem).")
            else:
                # CABEÇALHO ATUALIZADO PARA BATER CERTO COM AS 2 COLUNAS
                cabecalho = "Tópico ou Material | Especificação Técnica e Regras\n"
                resultado_com_cabecalho = cabecalho + relatorio_final
                st.download_button("📥 Descarregar (TXT)", data=resultado_com_cabecalho, file_name="Auditoria_PDF_Blocotelha.txt")

        except Exception as e:
            st.error(f"Erro no sistema ou de ligação ao modelo: {e}")
    else:
        st.warning("⚠️ Carrega primeiro o ficheiro PDF.")