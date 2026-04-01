from langchain_openai import ChatOpenAI
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
import json

# ============================================================
# .env loader
# ============================================================
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


# ============================================================
# Streamlit UI
# ============================================================
st.set_page_config(page_title="BlocoAI - Orçamentação", layout="wide", page_icon="🏗️")
st.sidebar.image("https://img.icons8.com/fluency/96/structural.png", width=80)
st.sidebar.title("Configurações")

modo_execucao = st.sidebar.radio("Ligação", ["Local", "API Key", "Groq"], index=0)

ROWS_PER_CHUNK = 50 

if modo_execucao == "API Key":
    api_key_default = os.getenv("CHATGPT_API_KEY", "")
    api_key_input = st.sidebar.text_input("🔑 API Key OpenAI", value="", type="password")
    api_key = api_key_input.strip() or api_key_default.strip()
    modelo_selecionado = st.sidebar.selectbox("🧠 Modelo OpenAI", ["gpt-4o-mini", "gpt-4", "gpt-3.5-turbo"])
    
elif modo_execucao == "Groq":
    groq_api_key_default = os.getenv("GROQ_API_KEY", "")
    groq_api_key_input = st.sidebar.text_input("🔑 API Key Groq", value="", type="password")
    groq_api_key = groq_api_key_input.strip() or groq_api_key_default.strip()
    modelo_selecionado = st.sidebar.selectbox("🧠 Modelo Groq", ["gpt-oss-120b"])
# ============================================================
# PDF reader (texto)
# ============================================================
def read_pdf_ultra_clean(uploaded_file) -> str:
    """Lê o PDF mantendo o layout (layout=True ajuda em tabelas)."""
    text_lines = []
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True)
            if text:
                linhas = [linha.rstrip() for linha in text.split('\n') if linha.strip()]
                text_lines.extend(linhas)
    return "\n".join(text_lines)

# ============================================================
# Spreadsheet reader (TEXTO SIMPLES EM LINHAS | OTIMIZADO)
# ============================================================
# ============================================================
# Spreadsheet reader (TEXTO SIMPLES EM LINHAS | OTIMIZADO)
# ============================================================
def read_excel_ultra_clean(uploaded_file, max_cols_per_row=12) -> str:
    """
    Excel/CSV -> texto com rastreabilidade + coluna=valor.
    - max_cols_per_row limita quantos campos mandas (poupa tokens).
    """
    text_lines = []

    # CSV ou Excel
    if uploaded_file.name.lower().endswith('.csv'):
        df = pd.read_csv(uploaded_file, keep_default_na=False).fillna("").astype(str)
        dfs = {"CSV Data": df}
    else:
        xls = pd.ExcelFile(uploaded_file)
        dfs = {sheet: xls.parse(sheet).fillna("").astype(str) for sheet in xls.sheet_names}

    # normalizar header (evita "nan")
    def clean_col(c, i):
        c = str(c).strip()
        return c if c and c.lower() != "nan" else f"col_{i+1}"

    for sheet, df in dfs.items():
        df.columns = [clean_col(c, i) for i, c in enumerate(df.columns)]

        for idx, row in df.iterrows():
            numero_linha = idx + 2  # assumindo header na linha 1

            pairs = []
            for col in df.columns:
                v = str(row[col]).strip()
                if v.lower() in ["", "nan", "none", "0", "0.0"]:
                    continue

                # compacta: "Description" grande fica, mas limita campos
                pairs.append(f"{col}={v}")
                if len(pairs) >= max_cols_per_row:
                    break

            if len(pairs) >= 2:
                text_lines.append(f"[{sheet}@L{numero_linha}] " + " | ".join(pairs))

    # remove duplicados preservando ordem
    return "\n".join(list(dict.fromkeys(text_lines)))
# ============================================================
# JSON parsing helpers
# ============================================================
def strip_code_fences(text: str) -> str:
    text = text.strip()
    # Remove markdown code blocks
    text = re.sub(r"json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*", "", text, flags=re.IGNORECASE)
    # Remove "json" prefix if present
    text = re.sub(r"^json\s*", "", text, flags=re.IGNORECASE)
    return text.strip()

def safe_parse_json_list(raw: str):
    """
    Extrai e parseia JSON array de forma robusta.
    Se falhar, tenta extrair objetos JSON válidos individuais.
    Trata JSON truncado adicionando fechadores em falta.
    """
    import re
    
    cleaned = strip_code_fences(raw)
    
    if not cleaned.strip():
        st.warning("⚠️ Resposta vazia do LLM.")
        return []
    
    # Tenta encontrar o array JSON
    first = cleaned.find("[")
    last = cleaned.rfind("]")
    
    # Se não encontrou ] mas encontrou [, tenta fechar o array
    if first != -1 and last == -1:
        st.warning("⚠️ JSON truncado (sem fechador ]). A tentar completar...")
        json_str = cleaned[first:] + "]"
    elif first == -1 or last == -1 or last <= first:
        st.warning("⚠️ Nenhum array JSON encontrado. A procurar objetos individuais...")
        json_str = None
    else:
        json_str = cleaned[first:last + 1]
    
    # Tenta parsear o JSON completo
    if json_str:
        try:
            data = json.loads(json_str)
            
            # Se recebeu um dict em vez de list, converte
            if isinstance(data, dict):
                data = [data]
            elif not isinstance(data, list):
                st.warning(f"⚠️ JSON não é lista. Tipo: {type(data)}. Retornando lista vazia.")
                return []
            
            return data
            
        except json.JSONDecodeError as e:
            st.warning(f"⚠️ JSON inválido ({str(e)[:50]}...). A tentar recuperar objetos parciais...")
    
    # FALLBACK: Extrai objetos JSON { } válidos individuais
    # Usa regex mais inteligente para encontrar objetos JSON completos
    pattern = r'\{[^{}]*?(?:"[^"]*?"\s*:\s*[^,}]*)[^{}]*?\}'
    matches = re.findall(pattern, cleaned)
    
    recovered = []
    for match in matches:
        try:
            # Tenta limpar o objeto se tiver vírgula pendente
            obj_clean = match.rstrip(',').strip()
            obj = json.loads(obj_clean)
            if isinstance(obj, dict):
                recovered.append(obj)
        except json.JSONDecodeError:
            pass  # Ignora objetos que não conseguimos parsear
    
    if recovered:
        st.success(f"✅ Recuperados {len(recovered)} objetos JSON válidos")
        return recovered
    else:
        st.error(f"❌ Falha ao parsear JSON. Raw (primeiros 800 chars):\n{raw[:800]}")
        return []

def normalize_item(item: dict, chunk_index: int) -> dict:
    return {
        "linha": item.get("linha", "") or "",
        "phase": item.get("phase", "") or "",
        "building": item.get("building", "") or "",
        "item": item.get("item", "") or "",
        "especificacao": item.get("especificacao", "") or "",
        "ecc": item.get("ecc", "") or ""
    }

# ============================================================
# LLM extraction (Texto em Linhas -> JSON output)
# ============================================================
def processar_excel_texto_json(texto_integral: str, llm, modo: str, linhas_por_chunk: int, notas_adicionais: str = ""):
    # Divide o textoão enorme de volta em linhas e agrupa-as
    linhas_totais = texto_integral.split('\n')
    chunks = [linhas_totais[i:i + linhas_por_chunk] for i in range(0, len(linhas_totais), linhas_por_chunk)]
    resultados = []

    st.markdown("### 📡 Monitor de Extração (Excel/CSV Texto → JSON)")
    progresso_bar = st.progress(0)
    status_text = st.empty()
    tabela_placeholder = st.empty()

    # Adicionar notas adicionais ao sistema prompt se fornecidas
    system_content = (
        "You are a Senior Structural Steel Engineer.\n"
        "You receive plain text rows from a spreadsheet.\n"
        "Your task: extract ONLY steel-related items and their FULL technical specifications.\n\n"
        "CRITICAL OUTPUT RULE:\n"
        "- Output ONLY valid JSON.\n"
        "- No markdown, no explanations, no extra text.\n"
        "- JSON MUST be a LIST of objects.\n\n"
        "Deduplication:\n"
        "- If multiple rows represent the same item/spec, output it only once.\n"
        "- Never invent data.\n"
    )
    
    if notas_adicionais and notas_adicionais.strip() and notas_adicionais.strip() != "(Opcional)":
        system_content += f"\nADDITIONAL INSTRUCTIONS FROM USER:\n{notas_adicionais}\n"
    
    mensagem_sistema = SystemMessage(content=system_content)

    for i, chunk_lines in enumerate(chunks, start=1):
        status_text.text(f"🔍 Ficheiro: Bloco {i} de {len(chunks)}...")
        progresso_bar.progress(i / len(chunks))

        # Volta a juntar as linhas do chunk
        chunk_text = "\n".join(chunk_lines)

        with st.expander(f"👁️ Ver texto enviado (Bloco {i})", expanded=False):
            st.text(chunk_text[:6000] + ("\n...\n" if len(chunk_text) > 6000 else ""))

        prompt_bloco = f"""
You are a Senior Structural Steel Engineer analyzing spreadsheet rows exported as text.

Each row is formatted like:
[Sheet@L<number>] field=value | field=value | field=value | ...

Your job is to extract ONLY steel-related line items and their technical specifications.

How to interpret rows (do NOT assume fixed column names):
- Phase: any field value matching the pattern "Phase <number>" (e.g., "Phase 1", "Phase 2").
- Building: a 3-letter building code (e.g., FSA, DCH, ABC) that appears as a standalone token or as a short field value. Prefer values that repeat across many rows.
- Elemental cost classification (ECC): any field whose value indicates a cost classification/category; treat a row as steel-related ONLY if that value contains the word "Steel" (case-insensitive).
- Item description / technical spec: text fields that describe scope/material/specification (e.g., beams, columns, plates, bolts 8.8/10.9, EN standards, coatings, fire rating).

Extraction rules:
- Include ONLY steel-related items (based on ECC containing "Steel").
- Extract:
  1) building (if found)
  2) phase (if found)
  3) item (short name of the steel element/system)
  4) especificacao (full technical specification text found in the row: grades S235/S355, EXC2/EXC3, EN/BS standards, coatings, galvanizing, paint micron, fire rating R30/R60/R120, bolts EN 14399 8.8/10.9, etc.)
  5) ecc (the classification value that triggered the steel filter)
  6) linha (the line reference from the prefix: use "L<number>" from [Sheet@L<number>])
- Do NOT include quantities, prices, totals, or units unless they are part of a technical specification (e.g., "10mm" thickness is allowed).
- Deduplicate: if the same item with the same especificacao appears multiple times, output it only once. If duplicates have different linha values, keep the first linha only.
- Never infer or invent missing values. If building/phase cannot be determined from the row, output them as empty string "".

OUTPUT RULES (STRICT):
- Output ONLY a valid JSON array. No markdown, no explanations, no extra text.
- If no steel items are found, output: []
- JSON schema:
[
  {{
    "item": "...",
    "building": "...",
    "phase": "...",
    "especificacao": "...",
    "ecc": "...",
    "linha": "L..."
  }}
]
SPREADSHEET DATA:
{chunk_text}

JSON OUTPUT:
""".strip()

        try:
            res = llm.invoke([mensagem_sistema, HumanMessage(content=prompt_bloco)])
            raw = res.content.strip() if res and res.content else ""
            
            if not raw:
                st.warning(f"⚠️ Bloco {i}: LLM retornou resposta vazia")
                continue

            # Debug: mostrar a resposta bruta
            with st.expander(f"🔧 Debug: Resposta bruta LLM (Bloco {i})", expanded=False):
                st.text(raw[:1500] + ("\n...\n" if len(raw) > 1500 else ""))

            items = safe_parse_json_list(raw)

            if items:  # Só adiciona se houver items
                for it in items:
                    resultados.append(normalize_item(it, chunk_index=i))
                st.success(f"✅ Bloco {i}: Extraídos {len(items)} items")
            # Se não houver items, não mostra nada (silencioso)

            if resultados:
                df = pd.DataFrame(resultados)
                tabela_placeholder.dataframe(df, width='stretch', height=420)

            # Rate-limit guard for Groq
            if modo == "API Key" and i < len(chunks) - 1:
                st.toast("⏳ A respeitar limites da API (pausa 35s)...")
                time.sleep(35)

        except Exception as e:
            st.error(f"❌ Bloco {i}: Erro na chamada LLM: {e}")
            
            if "429" in str(e):
                st.warning("🚨 Limite atingido. A tentar recuperar em 60 segundos...")
                time.sleep(60)

    return resultados

# ============================================================
# Main UI
# ============================================================
st.title("🏗️ BlocoAI: Extrator")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Ficheiro")
    file_uploaded = st.file_uploader("Carrega o ficheiro do cliente", type=["xlsx", "xls", "csv", "pdf"])

with col2:
    st.subheader("2. Notas")
    st.info("Modo 'Engenheiro de Aço' ativo. Output: JSON + tabela.")
    guia_input = st.text_area("Instruções adicionais (opcional):", height=100)

if st.button("🚀 Iniciar Análise"):
    if not file_uploaded:
        st.warning("⚠️ Carrega primeiro um ficheiro.")
        st.stop()

    try:
        # Escolher LLM
        # Escolher LLM
        if modo_execucao == "API Key":
                if not api_key.strip():
                    st.error("⚠️ API Key em falta. Coloca-a na barra lateral.")
                    st.stop()
                llm = ChatOpenAI(model=modelo_selecionado, api_key=api_key, temperature=0.1)

        elif modo_execucao == "Groq":
                if not groq_api_key.strip():
                    st.error("⚠️ API Key Groq em falta. Coloca-a na barra lateral.")
                    st.stop()
                llm = ChatGroq(model="openai/gpt-oss-120b", api_key=groq_api_key, temperature=0.1)

            
        else:
            if modo_execucao == "Local":
                base_url_ollama = "[http://127.0.0.1:11434](http://127.0.0.1:11434)"

            llm = ChatOllama(
                model=modelo_selecionado,
                base_url=base_url_ollama,
                temperature=0.1,
                num_ctx=16384
            )

        if file_uploaded.name.lower().endswith((".xlsx", ".xls", ".csv")):
            with st.spinner("A ler ficheiro (Excel/CSV) e extrair texto (separado por '|')..."):
                texto_linhas_sujas = read_excel_ultra_clean(file_uploaded)
                num_linhas = len(texto_linhas_sujas.split('\n'))
                st.success(f"Ficheiro processado! Total de linhas únicas: {num_linhas}")

            with st.expander("👁️ Amostra do Texto Gerado (5 linhas)", expanded=False):
                st.text("\n".join(texto_linhas_sujas.split('\n')[:5]))

            resultados_json = processar_excel_texto_json(
                texto_integral=texto_linhas_sujas,
                llm=llm,
                modo=modo_execucao,
                linhas_por_chunk=ROWS_PER_CHUNK,
                notas_adicionais=guia_input
            )

        st.markdown("---")
        st.subheader("📊 Tabela Final")
        df_final = pd.DataFrame(resultados_json)
        st.dataframe(df_final, width='stretch', height=520)

        st.subheader("📥 Download JSON")
        json_str = json.dumps(resultados_json, ensure_ascii=False, indent=2)
        st.download_button(
            "📥 Descarregar JSON",
            data=json_str,
            file_name="Extracao_Aco.json",
            mime="application/json"
        )

    except Exception as e:
        st.error(f"Erro no sistema ou de ligação: {e}")