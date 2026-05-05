from langchain_ollama import ChatOllama

DEFAULT_MODEL = "llama3"
DEFAULT_TEMPERATURE = 0.2

def get_llm(model=DEFAULT_MODEL, temperature=DEFAULT_TEMPERATURE):
    return ChatOllama(model=model, temperature=temperature)
