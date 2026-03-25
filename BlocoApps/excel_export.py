import argparse
import json
from pathlib import Path
import pandas as pd

def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    workspace_dir = script_dir.parent

    # Definições padrão mais genéricas
    default_input = workspace_dir / "Extracao_Aco.json"
    default_output = workspace_dir / "Orcamento_Estruturado.xlsx"

    parser = argparse.ArgumentParser(
        description="Exporta o JSON do BlocoAI para um Excel limpo, estruturado e formatado.",
    )
    parser.add_argument("-i", "--input", default=str(default_input), help="Caminho do arquivo JSON de entrada.")
    parser.add_argument("-o", "--output", default=str(default_output), help="Caminho do arquivo Excel de saída (.xlsx).")
    return parser.parse_args()


def list_to_text(value):
    """Converte arrays do JSON (como blocos e processos) numa string separada por vírgulas."""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return value


def export_json_to_excel(input_path: Path, output_path: Path) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"Arquivo JSON não encontrado: {input_path}")

    with input_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("O JSON de entrada deve ser uma lista de objetos.")

    # O json_normalize espalma magicamente dicionários aninhados (ex: propriedades ficam properties.grade)
    df = pd.json_normalize(data)

    # Converte todas as listas para texto para não quebrar a exportação para o Excel
    for col in df.columns:
        df[col] = df[col].apply(list_to_text)

    # --- MAPEAR E LIMPAR NOMES PARA APRESENTAÇÃO PROFISSIONAL ---
    rename_map = {
        "source_block": "Blocos de Origem",
        "category": "Categoria Matriz",
        "element": "Elemento Principal",
        "properties.grade": "Grau de Aço (Grade)",
        "properties.execution_class": "Classe Execução",
        "properties.standard": "Norma (Standard)",
        "coating": "Revestimento",
        "fire_protection": "Proteção ao Fogo",
        "processes": "Processos Mapeados",
        "raw_item": "Item Original",
        "raw_spec": "Especificação Completa (BOQ)",
        "notes": "Notas",
        "confidence": "Confiança IA"
    }
    
    # Renomeia as colunas que existirem no dataframe
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # Preenche valores vazios/nulos com string vazia (Fica muito mais limpo no Excel)
    df = df.fillna("")

    # --- ORDENAÇÃO LÓGICA DAS COLUNAS ---
    ordem_desejada = [
        "Blocos de Origem", "Categoria Matriz", "Elemento Principal", 
        "Grau de Aço (Grade)", "Classe Execução", "Norma (Standard)", 
        "Revestimento", "Proteção ao Fogo", "Processos Mapeados", 
        "Item Original", "Especificação Completa (BOQ)", "Notas", "Confiança IA"
    ]
    
    colunas_presentes = [col for col in ordem_desejada if col in df.columns]
    colunas_extras = [col for col in df.columns if col not in colunas_presentes]
    df = df[colunas_presentes + colunas_extras] # Garante que nada se perde

    # --- GRAVAR NO EXCEL COM AUTO-AJUSTE VISUAL ---
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Orçamento Aço')
        
        # Aceder à folha (worksheet) para formatar
        worksheet = writer.sheets['Orçamento Aço']
        
        # Ajustar as larguras dinamicamente para não ficar "esmagado"
        for col in worksheet.columns:
            max_length = 0
            column_letter = col[0].column_letter
            
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            
            # Dá uma margem e define um limite máximo de largura (ex: 50) para textos muito longos
            adjusted_width = min(max_length + 2, 60)
            worksheet.column_dimensions[column_letter].width = adjusted_width


def main() -> None:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if output_path.suffix.lower() !=