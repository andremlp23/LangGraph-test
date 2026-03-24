import streamlit as st
import pandas as pd
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

# --- 1. CONFIGURAÇÃO DA INTERFACE ---
st.set_page_config(page_title="BlocoAI - Orçamentação", layout="wide", page_icon="🏗️")

st.sidebar.image("https://img.icons8.com/fluency/96/structural.png", width=80)
st.sidebar.title("Configurações do Servidor")

modo_execucao = st.sidebar.radio(
    "Ligação",
    ["Remoto", "Local"],
    index=0,
)

torre_ip = st.sidebar.text_input("IP da Torre Ollama", value="100.105.95.121")
modelo_selecionado = st.sidebar.selectbox("LLM", ["qwen3.5:9b", "llama3.2:3b"])


# --- 2. LEITURA INTELIGENTE DE EXCEL ---
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

# --- 3. MOTOR DE EXTRAÇÃO EM TEMPO REAL ---
def processar_por_chunks_exaustivo(texto_integral: str, guia_texto: str, llm):
    tamanho_chunk = 12000 
    chunks = [texto_integral[i:i + tamanho_chunk] for i in range(0, len(texto_integral), tamanho_chunk)]
    
    notas_recolhidas = []
    
    st.markdown("### 📡 Monitor de Extração em Tempo Real")
    progresso_bar = st.progress(0)
    status_text = st.empty()
    
    # Esta caixa vai atualizar-se sozinha bloco a bloco
    caixa_resultados = st.empty() 

    # MENSAGEM DE SISTEMA (Modo Robô Ativado - Em Inglês)
    mensagem_sistema = SystemMessage(
        content=(
            "You are a strict data extraction script. You do not speak. You do not explain. "
            "You ONLY output pipe-separated text lines. Do not use bullet points, bold text (**), or headers."
        )
    )

    for i, chunk in enumerate(chunks):
        status_text.text(f"🔍 A analisar: Bloco {i+1} de {len(chunks)}...")
        progresso_bar.progress((i + 1) / len(chunks))

        # Mostrar o texto enviado pelo Python num expansor
        with st.expander(f"👁️ Ver o Texto Cru enviado no Bloco {i+1}", expanded=False):
            st.text(chunk)

        # MENSAGEM HUMANA (Com Exemplo Exato para forçar o formato)
        mensagem_humana = HumanMessage(
            content=(
                "Extrai os materiais de construção, normas e quantidades do TEXTO EXCEL.\n"
                "Mapeia cada um para a categoria correta da MATRIZ.\n\n"
                "FORMATO OBRIGATÓRIO (Usa apenas este formato de linha única, sem qualquer outro texto):\n"
                "Categoria da Matriz | Nome do Material | Especificações Técnicas (Normas, Marcas, Espessuras) | Quantidade | Unidade\n\n"
                "EXEMPLOS DE OUTPUT ESPERADO:\n"
                "4. MATERIAL DE BASE | Aço Estrutural | Grau S355, Exc Class 2 | 711.0 | tn\n"
                "10. COMPLEXO COBERTURA/FACHADA | Painel de Cobertura | Euroclad Top Deck, 280mm | 1942.0 | m2\n"
                "10. COMPLEXO COBERTURA/FACHADA | Isolamento Mineral | Sikatherm MW, 250mm | N/A | N/A\n\n"
                "Se não houver materiais no texto, escreve apenas: SEM MATERIAIS NESTE BLOCO.\n\n"
                f"### MATRIZ:\n{guia_texto}\n\n"
                f"### TEXTO EXCEL:\n{chunk}\n\n"
                "### OUTPUT (Apenas as linhas formatadas):"
            )
        )

        try:
            res = llm.invoke([mensagem_sistema, mensagem_humana])
            resposta = res.content.strip()
            
            # Limpa lixo se o modelo disser "Sem materiais" e adiciona aos resultados
            if "SEM MATERIAIS" not in resposta.upper() and len(resposta) > 20:
                # Adicionamos a resposta pura sem mais texto!
                notas_recolhidas.append(resposta)
            
            # Atualiza a caixa de resultados em tempo real
            texto_acumulado = "\n".join(notas_recolhidas)
            if texto_acumulado.strip():
                caixa_resultados.text_area(
                    f"Resultados Acumulados (Processado até ao Bloco {i+1}):", 
                    value=texto_acumulado, 
                    height=400
                )
                
        except Exception as e:
            notas_recolhidas.append(f"⚠️ Erro ao processar o bloco {i+1}: {e}")
            
    return "\n".join(notas_recolhidas)
def read_pdf_ultra_clean(uploaded_file) -> str:
    """Lê o PDF mantendo o layout das tabelas (crucial para as quantidades não se separarem dos materiais)."""
    text_lines = []
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            # O layout=True é a magia que mantém os espaços entre colunas!
            text = page.extract_text(layout=True) 
            if text:
                # Limpa linhas vazias mas mantém a estrutura da linha
                linhas = [linha.strip() for linha in text.split('\n') if linha.strip()]
                text_lines.extend(linhas)
                
    return "\n".join(text_lines) 
# --- 4. INTERFACE PRINCIPAL ---
st.title("🏗️ BlocoAI: Extrator de Excel")
st.markdown("Auditoria automática com base na Matriz de Referência.")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Ficheiro de Orçamento (Excel)")
    file_excel = st.file_uploader("Carrega o ficheiro do cliente", type=["xlsx", "xls"])

with col2:
    st.subheader("2. Matriz de Auditoria")
    guia_padrao = """1. CLASSE EXECUÇÃO: EXC2, EXC3, EXC4 | Prazos.
2. RECURSOS: Protótipo, Cálculo, Topografia.
3. TOLERÂNCIAS: Fabrico (EN 1090, Soldadura, Pintura), Montagem.
4. MATERIAL DE BASE: Origem (Europa, UK, etc) | Tipo/Grade de Aço (S235 a S460, JR/J0/J2) | Normas.
5. PARAFUSOS: Fixações (EN 14399, 8.8, 10.9) | Rosca, Tratamento, Porcas.
6. CHUMBADOUROS: Composição (Métrica, Comprimento, Classe 8.8/10.9), Grout.
7. PROTEÇÃO ANTI CORROSIVA: Corrosividade, Decapagem, Galvanização, Espessura mínima.
8. PROTEÇÃO AO FOGO: Intumescente (R30, R60, R120), Espessura, Epoxy.
9. GRADIL / STEPLARM: Tipo (Prensado, PRFV), Malha, Vão máx, Galvanizado/Lacado.
10. COMPLEXO COBERTURA/FACHADA: Térmica, Fogo, Espessuras de chapa e isolamento, Marcas (Euroclad, Kingspan, etc).
11. LOGÍSTICA: Incoterms (EXW, DAP, DDP, etc)."""
    
    guia_input = st.text_area("Podes editar a matriz antes de analisar:", value=guia_padrao, height=250)

if st.button("🚀 Iniciar Análise Completa"):
    if file_excel:
        try:
            if modo_execucao == "Local":
                base_url_ollama = "http://127.0.0.1:11434"
            else:
                base_url_ollama = f"http://{torre_ip}:11434"

            # Temperatura a 0.1 para evitar bloqueios do LLM
            llm = ChatOllama(model=modelo_selecionado, base_url=base_url_ollama, temperature=0.1)
            
            with st.spinner("A limpar e comprimir as linhas do Excel..."):
                texto_completo = read_excel_ultra_clean(file_excel)
                st.success(f"Excel processado! Texto comprimido para a IA ler.")

            # --- Extração (Isto faz o trabalho pesado todo) ---
            notas_finais = processar_por_chunks_exaustivo(texto_completo, guia_input, llm)
            
            st.markdown("---")
            st.subheader("📄 Relatório Técnico Final (Puro)")

            # Apresentamos a lista crua final
            if len(notas_finais.strip()) < 10:
                st.warning("⚠️ A IA não extraiu dados válidos após analisar todo o documento.")
            else:
                st.download_button("📥 Descarregar Dados (TXT)", data=notas_finais, file_name="Auditoria_Blocotelha_Pura.txt")

        except Exception as e:
            st.error(f"Erro no sistema ou de ligação à Torre: {e}")
    else:
        st.warning("⚠️ Carrega primeiro o ficheiro Excel na coluna da esquerda.")