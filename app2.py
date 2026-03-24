import streamlit as st
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage

st.title("🩺 Diagnóstico do Motor Ollama")

modo = st.radio("Onde está a correr o Ollama?", ["Local", "Remoto"])
ip = st.text_input("IP da Torre (se remoto)", value="100.105.95.121")
modelo = st.selectbox("Modelo a testar", ["qwen3.5:9b", "llama3.2:3b"])

if st.button("🚀 Testar Comunicação"):
    try:
        # Define o endereço com base na escolha
        url = "http://127.0.0.1:11434" if modo == "Local" else f"http://{ip}:11434"
        
        st.info(f"A tentar ligar a: {url} usando o modelo {modelo}...")
        
        # Conecta ao motor
        llm = ChatOllama(model=modelo, base_url=url, temperature=0)
        
        # O prompt mais básico do mundo
        pergunta = "Responde apenas com a palavra: SUCESSO."
        
        res = llm.invoke([HumanMessage(content=pergunta)])
        
        # Mostra a resposta crua
        st.success(f"A IA respondeu: {res.content}")
        
    except Exception as e:
        st.error("🚨 Ocorreu um erro técnico de ligação ou execução!")
        st.code(str(e)) # Isto vai imprimir o erro técnico real para nós vermos