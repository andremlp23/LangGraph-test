import streamlit as st
import pandas as pd
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage

# --- 1. CONFIGURAÇÃO DA INTERFACE ---
st.set_page_config(page_title="BlocoAI - Orçamentação", layout="wide", page_icon="🏗️")

st.sidebar.image("https://img.icons8.com/fluency/96/structural.png", width=80)
st.sidebar.title("Configurações do Servidor")

torre_ip = st.sidebar.text_input("IP da Torre Ollama", value="100.105.95.121")
modelo_selecionado = st.sidebar.selectbox("Modelo de IA", ["qwen3.5:9b", "llama3.2:3b"])

st.sidebar.markdown("---")
st.sidebar.caption("Dica: Usa o Qwen para maior precisão e o Llama para maior velocidade.")

# --- 2. LEITURA INTELIGENTE DE EXCEL ---
def read_excel_ultra_clean(uploaded_file) -> str:
    """Lê o Excel, junta as colunas na mesma linha (para manter Qty e Unit ligados ao Item) e remove lixo."""
    xls = pd.ExcelFile(uploaded_file)
    text_lines = []
    
    for sheet in xls.sheet_names:
        df = xls.parse(sheet).astype(str)
        
        for _, row in df.iterrows():
            # Limpa células vazias ou irrelevantes
            valores = [v.strip() for v in row if v.strip().lower() not in ['nan', 'none', '0.0', '0', '']]
            if len(valores) > 1:  # Ignora linhas que só têm 1 palavra solta
                # O separador ' | ' ajuda a IA a perceber que são colunas diferentes (Ex: Item | Qty | Unit)
                linha_texto = " | ".join(valores)
                text_lines.append(linha_texto)
                
    # Remove linhas exatamente iguais (subtotais repetidos, cabeçalhos de página, etc.)
    return "\n".join(list(dict.fromkeys(text_lines)))

# --- 3. MOTOR DE EXTRAÇÃO BILINGUE ---
def processar_por_chunks_exaustivo(texto_integral: str, guia_texto: str, llm):
    tamanho_chunk = 6000 # Bloco otimizado
    chunks = [texto_integral[i:i + tamanho_chunk] for i in range(0, len(texto_integral), tamanho_chunk)]
    
    notas_recolhidas = []
    progresso_bar = st.progress(0)
    status_text = st.empty()

    for i, chunk in enumerate(chunks):
        status_text.text(f"🔍 Auditoria Bilingue: Bloco {i+1} de {len(chunks)}...")
        progresso_bar.progress((i + 1) / len(chunks))
        
        prompt_bloco = (
            "Atua como um Engenheiro Orçamentista Sénior a fazer uma auditoria rigorosa.\n"
            "Lê o EXCERTO do Excel (em Inglês) e cruza com as categorias da MATRIZ (em Português).\n"
            "O teu objetivo é extrair o MÁXIMO DE DETALHE TÉCNICO, MAS COM CONTEXTO ABSOLUTO.\n\n"
            "REGRA DE OURO: NUNCA extraias números, medidas, normas ou características soltas.\n"
            "Toda a espessura, medida, grau de aço ou tratamento tem obrigatoriamente de estar descrita junto ao item a que pertence.\n"
            "Exemplo ERRADO: '240mm', 'S355', 'Galvanizado', '10.9'.\n"
            "Exemplo CORRETO: 'Painel de fachada Kingspan com 240mm de espessura', 'Perfil de aço grau S355', 'Parafuso classe 10.9 galvanizado'.\n\n"
            "Para cada elemento encontrado, cria um bloco com esta estrutura:\n"
            "Categoria da Matriz: [Nome da categoria correspondente]\n"
            "Item Principal: [O que é o material/peça?]\n"
            "Especificações Contextualizadas: [Descreve as dimensões, normas, marcas e tratamentos associados EXCLUSIVAMENTE a este item]\n"
            "Quantidade: [Valor de Qty da mesma linha] | Unidade: [Unit da mesma linha]\n"
            "---\n\n"
            f"### MATRIZ DE REFERÊNCIA:\n{guia_texto}\n\n"
            f"### EXCERTO DO EXCEL:\n{chunk}\n\n"
            "### DADOS EXTRAÍDOS (Rigor e Contexto):"
        )
        
        res = llm.invoke([HumanMessage(content=prompt_bloco)])
        
        # Filtro permissivo: guarda qualquer resposta que tenha mais de 15 caracteres.
        resposta = res.content.strip()
        if len(resposta) > 15:
            notas_recolhidas.append(resposta)
            
    return "\n".join(notas_recolhidas)

# --- 4. INTERFACE PRINCIPAL ---
st.title("🏗️ BlocoAI: Extrator de Cadernos de Encargos")
st.markdown("Auditoria automática com base na Matriz de Referência da Blocotelha.")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Ficheiro de Orçamento (Excel)")
    file_excel = st.file_uploader("Carrega o ficheiro do cliente", type=["xlsx", "xls"])

with col2:
    st.subheader("2. Matriz de Auditoria")
    # A Matriz Gigante e Detalhada que definimos
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

if st.button("🚀 Iniciar Auditoria Completa"):
    if file_excel:
        try:
            llm = ChatOllama(model=modelo_selecionado, base_url=f"http://{torre_ip}:11434", temperature=0)
            
            with st.spinner("A limpar e comprimir as linhas do Excel..."):
                texto_completo = read_excel_ultra_clean(file_excel)
                st.success(f"Excel processado! Texto comprimido para a IA ler.")

            # --- Extração (Isto faz o trabalho pesado todo) ---
            notas_finais = processar_por_chunks_exaustivo(texto_completo, guia_input, llm)
            
            st.empty() # Limpa as mensagens da barra de progresso
            st.markdown("---")
            st.subheader("📄 Relatório Técnico e Quantidades (Puro)")

            # Apresentamos a lista crua, limpa e exata
            if len(notas_finais.strip()) < 10:
                st.warning("⚠️ A IA não extraiu dados válidos. Verifica o conteúdo do Excel.")
            else:
                st.text_area("Resultado Direto da Auditoria:", value=notas_finais, height=500)
                
                # O botão de download guarda exatamente o que vês na caixa
                st.download_button("📥 Descarregar Dados (TXT)", data=notas_finais, file_name="Auditoria_Blocotelha_Pura.txt")

        except Exception as e:
            st.error(f"Erro no sistema ou de ligação à Torre: {e}")
    else:
        st.warning("⚠️ Carrega primeiro o ficheiro Excel do cliente na coluna da esquerda.")