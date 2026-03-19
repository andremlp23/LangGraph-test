from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langchain_ollama import ChatOllama
from langgraph.graph.message import add_messages

# 1. O ESTADO: A memória do nosso agente
# Usamos 'add_messages' para ele ir acumulando o histórico da conversa
class EstadoAgente(TypedDict):
    messages: Annotated[list, add_messages]

# 2. O MODELO: Ligar à torre via Tailscale
llm = ChatOllama(
    model="qwen3.5:9b", 
    base_url="http://100.105.95.121:11434", # O IP da tua torre
    temperature=1
)

# 3. OS NÓS (NODES): A lógica do que o agente faz
def chamar_modelo(state: EstadoAgente):
    resposta = llm.invoke(state["messages"])
    return {"messages": [resposta]}
def node4(state):
    pass
workflow.add_node("node_4", node_4)  # Add node for node_4
# 4. Prepara o input para o teu agente LangGraph
    inputs = {
        "messages": [
            # A instrução mestre que o modelo tem de obedecer:
            ("system", "És um agente que lê documentos e responde a perguntas. "
            "Responde apenas com o conteúdo do documento, sem explicações ou introduções."),
            # A pergunta real do utilizador:
            ("user", pergunta_utilizador)
        ] 
    }

# 4. CONSTRUIR O GRAFO
workflow = StateGraph(EstadoAgente)
workflow.add_node("assistente", assistente)  # Add node for assistente

# Definir o caminho: INÍCIO -> assistente -> FIM
workflow.add_edge(START, "assistente")
workflow.add_edge("assistente", END)

# 5. COMPILAR O AGENTE (É aqui que a variável 'agente' nasce!)
agente = workflow.compile()

# ====================================================================
# 6. O CICLO INTERATIVO (O teu terminal)
# ====================================================================

print("\n" + "="*50)
print("🤖 Teste LangGraph + Qwen (via Tailscale)")
print("Escreve 'sair' a qualquer momento para terminar.")
print("="*50 + "\n")

while True:
    pergunta_utilizador = input("Tu 👤: ")
    
    if pergunta_utilizador.strip().lower() in ['sair', 'exit', 'quit']:
        print("A encerrar o teste. Adeus! 👋")
        break
        
    if not pergunta_utilizador.strip():
        continue
        
    print("A processar na torre ⚙️ ...")
    
    # Prepara o input no formato que o EstadoAgente espera (uma lista de mensagens)
    inputs = {
        "messages": [("user", pergunta_utilizador)] 
    }
    
    try:
        # Agora o "agente" já existe e pode ser invocado!
        resultado = agente.invoke(inputs)
        
        # Vai buscar o conteúdo da última mensagem (a resposta do Qwen)
        resposta_final = resultado["messages"][-1].content
        print(f"\nQwen : {resposta_final}\n")
        print("-" * 50)
        
    except Exception as e:
        print(f"\n Erro de ligação: {e}")
        print("-> Confirma se o IP do Tailscale está correto no base_url.")
        print("-> Confirma se configuraste o OLLAMA_HOST=0.0.0.0 na torre.\n")
        break
workflow.add_edge("start", "node_4")
workflow.add_edge("node_4", "end")