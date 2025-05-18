# Bondage: A Polyglot Code Transmutation Engine 

# 🛡️ CLI Modes: API + No-API
# - Use --no-api to bypass OpenAI and enter Python code manually
# - Saves output to ./outputs/{language}.txt
# - Secure API handling via OPENAI_API_KEY only

import os
import sys
import requests
import json
import ast
import subprocess
import tempfile
from typing import Dict, Any, List

# --- Abstract Syntax Tree Node ---
class UASTNode:
    def __init__(self, node_type: str, name: str = "", children: List[Any] = None, meta: Dict[str, Any] = None):
        self.node_type = node_type
        self.name = name
        self.children = children or []
        self.meta = meta or {}

    def __repr__(self):
        return f"UASTNode({self.node_type}, {self.name}, {self.children})"


# --- GPT API Code Generation ---
def query_openai_for_code(prompt: str, api_key: str) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "gpt-4o",
        "messages": [
            {"role": "user", "content": f"Write the following logic in Python only. Be clean and minimal. {prompt}"}
        ]
    }
    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, data=json.dumps(body))
    if response.status_code == 200:
        return response.json()['choices'][0]['message']['content']
    else:
        return f"Error: {response.status_code} - {response.text}"


# --- Python AST to UAST conversion ---
def convert_ast_to_uast(py_node) -> UASTNode:
    if isinstance(py_node, ast.FunctionDef):
        children = [convert_ast_to_uast(stmt) for stmt in py_node.body]
        return UASTNode("function", name=py_node.name, children=children)
    elif isinstance(py_node, ast.Expr) and isinstance(py_node.value, ast.Call):
        call = py_node.value
        args = [ast.literal_eval(arg) if isinstance(arg, ast.Constant) else "expr" for arg in call.args]
        return UASTNode("call", name=call.func.id, meta={"args": args})
    return UASTNode("unknown")


def parse_python_to_uast(code: str) -> UASTNode:
    try:
        py_ast = ast.parse(code)
        return convert_ast_to_uast(py_ast.body[0]) if py_ast.body else UASTNode("empty")
    except Exception as e:
        return UASTNode("error", meta={"message": str(e)})


# --- Target Code Emitters ---
def emit_python_code(ast: UASTNode, indent: int = 0) -> str:
    ind = "    " * indent
    if ast.node_type == "function":
        body = "\n".join(emit_python_code(child, indent + 1) for child in ast.children)
        return f"{ind}def {ast.name}():\n{body}"
    elif ast.node_type == "call":
        args = ", ".join(repr(arg) for arg in ast.meta.get("args", []))
        return f"{ind}{ast.name}({args})"
    return ""


def emit_latex_code(ast: UASTNode) -> str:
    if ast.node_type == "function":
        body = "\\\n".join(emit_latex_code(child) for child in ast.children)
        return f"\\textbf{{def}} {ast.name}():\\\n{body}"
    elif ast.node_type == "call":
        args = ",~".join(str(arg).replace(" ", "~") for arg in ast.meta.get("args", []))
        return f"\\texttt{{{ast.name}({args})}}"
    return ""


def emit_cpp_code(ast: UASTNode) -> str:
    if ast.node_type == "function":
        body = "\n".join(emit_cpp_code(child) for child in ast.children)
        return f"void {ast.name}() {{\n{body}\n}}"
    elif ast.node_type == "call":
        args = ", ".join(str(arg) for arg in ast.meta.get("args", []))
        return f"    std::cout << {args} << std::endl;"
    return ""


def emit_js_code(ast: UASTNode) -> str:
    if ast.node_type == "function":
        body = "\n".join(emit_js_code(child) for child in ast.children)
        return f"function {ast.name}() {{\n{body}\n}}"
    elif ast.node_type == "call":
        args = ", ".join(str(arg) for arg in ast.meta.get("args", []))
        return f"    console.log({args});"
    return ""


# --- Compilation Validators ---
def validate_code(command: List[str], code: str, filename: str) -> bool:
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=filename) as temp:
            temp.write(code.encode())
            temp.flush()
            result = subprocess.run(command + [temp.name], capture_output=True)
            return result.returncode == 0
    except Exception:
        return False


def save_output_files(language_map: Dict[str, str], out_dir: str = "outputs"):
    os.makedirs(out_dir, exist_ok=True)
    for lang, code in language_map.items():
        with open(os.path.join(out_dir, f"{lang}.txt"), "w") as f:
            f.write(code)


# --- Main Execution Loop ---
if __name__ == "__main__":
    use_api = True
    if len(sys.argv) > 1 and sys.argv[1] == "--no-api":
        use_api = False

    if use_api:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("⚠️  No API key found. Please set OPENAI_API_KEY in your environment.")
            exit(1)
        prompt = input("Describe the logic you'd like to write: ")
        print("\n--- Requesting Python Code from OpenAI ---")
        python_code = query_openai_for_code(prompt, api_key)
    else:
        print("📝 Enter your Python function below. End with a blank line:")
        lines = []
        while True:
            line = input()
            if not line.strip():
                break
            lines.append(line)
        python_code = "\n".join(lines)

    print("\n--- Python Code ---")
    print(python_code)

    print("\n--- Converting to UAST ---")
    uast = parse_python_to_uast(python_code)

    # Emit for each target language
    languages = {
        "Python": emit_python_code(uast),
        "LaTeX": emit_latex_code(uast),
        "C++": emit_cpp_code(uast),
        "JavaScript": emit_js_code(uast)
    }

    save_output_files(languages)

    validators = {
        "Python": lambda code: validate_code(["python3", "-m", "py_compile"], code, ".py"),
        "LaTeX": lambda code: validate_code(["pdflatex", "-interaction=nonstopmode"], code, ".tex"),
        "C++": lambda code: validate_code(["g++", "-o", "/dev/null"], code, ".cpp"),
        "JavaScript": lambda code: validate_code(["node", "--check"], code, ".js")
    }

    print("\n--- Window Validation ---")
    for lang, code in languages.items():
        if validators[lang](code):
            print(f"✅ {lang} window stands.")
        else:
            print(f"💥 {lang} window shattered.")
