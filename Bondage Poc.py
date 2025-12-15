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
def _expr_to_str(node: ast.AST) -> str:
    try:
        return ast.unparse(node)  # type: ignore[attr-defined]
    except Exception:
        return "" if node is None else str(node)


def _call_to_uast(call: ast.Call) -> UASTNode:
    func_name = _expr_to_str(call.func)
    args = [_expr_to_str(arg) for arg in call.args]
    return UASTNode("call", name=func_name, meta={"args": args})


def convert_ast_to_uast(py_node) -> UASTNode:
    if isinstance(py_node, ast.Module):
        if not py_node.body:
            return UASTNode("empty")
        return convert_ast_to_uast(py_node.body[0])
    if isinstance(py_node, ast.FunctionDef):
        children = [convert_ast_to_uast(stmt) for stmt in py_node.body]
        params = [arg.arg for arg in py_node.args.args]
        return UASTNode("function", name=py_node.name, children=children, meta={"params": params})
    if isinstance(py_node, ast.Return):
        return UASTNode("return", meta={"value": _expr_to_str(py_node.value)})
    if isinstance(py_node, ast.Assign):
        target = _expr_to_str(py_node.targets[0]) if py_node.targets else ""
        value = _expr_to_str(py_node.value)
        return UASTNode("assign", meta={"target": target, "value": value})
    if isinstance(py_node, ast.Expr) and isinstance(py_node.value, ast.Call):
        return _call_to_uast(py_node.value)
    if isinstance(py_node, ast.Call):
        return _call_to_uast(py_node)
    if isinstance(py_node, ast.If):
        body = [convert_ast_to_uast(stmt) for stmt in py_node.body]
        orelse = [convert_ast_to_uast(stmt) for stmt in py_node.orelse]
        return UASTNode("if", children=body, meta={"condition": _expr_to_str(py_node.test), "orelse": orelse})
    if isinstance(py_node, ast.While):
        body = [convert_ast_to_uast(stmt) for stmt in py_node.body]
        return UASTNode("while", children=body, meta={"condition": _expr_to_str(py_node.test)})
    if isinstance(py_node, ast.For):
        body = [convert_ast_to_uast(stmt) for stmt in py_node.body]
        return UASTNode(
            "for",
            children=body,
            meta={"target": _expr_to_str(py_node.target), "iter": _expr_to_str(py_node.iter)},
        )
    return UASTNode("unknown", meta={"raw": type(py_node).__name__})


def parse_python_to_uast(code: str) -> UASTNode:
    try:
        py_ast = ast.parse(code)
        return convert_ast_to_uast(py_ast)
    except Exception as e:
        return UASTNode("error", meta={"message": str(e)})


# --- Target Code Emitters ---
def emit_python_code(ast: UASTNode, indent: int = 0) -> str:
    ind = "    " * indent
    if ast.node_type == "function":
        params = ", ".join(ast.meta.get("params", []))
        body_lines = [emit_python_code(child, indent + 1) for child in ast.children]
        if not body_lines:
            body_lines = [f"{ind}    pass"]
        body = "\n".join(body_lines)
        return f"{ind}def {ast.name}({params}):\n{body}"
    elif ast.node_type == "call":
        args = ", ".join(repr(arg) for arg in ast.meta.get("args", []))
        return f"{ind}{ast.name}({args})"
    elif ast.node_type == "assign":
        return f"{ind}{ast.meta.get('target', '')} = {ast.meta.get('value', '')}"
    elif ast.node_type == "return":
        return f"{ind}return {ast.meta.get('value', '')}"
    elif ast.node_type == "if":
        cond = ast.meta.get("condition", "")
        body_lines = [emit_python_code(child, indent + 1) for child in ast.children]
        if not body_lines:
            body_lines = [f"{ind}    pass"]
        body = "\n".join(body_lines)
        orelse_children = ast.meta.get("orelse", [])
        if orelse_children:
            else_body_lines = [emit_python_code(child, indent + 1) for child in orelse_children]
            else_body = "\n".join(else_body_lines or [f"{ind}    pass"])
            return f"{ind}if {cond}:\n{body}\n{ind}else:\n{else_body}"
        return f"{ind}if {cond}:\n{body}"
    elif ast.node_type == "while":
        cond = ast.meta.get("condition", "")
        body_lines = [emit_python_code(child, indent + 1) for child in ast.children]
        if not body_lines:
            body_lines = [f"{ind}    pass"]
        body = "\n".join(body_lines)
        return f"{ind}while {cond}:\n{body}"
    elif ast.node_type == "for":
        target = ast.meta.get("target", "")
        iterable = ast.meta.get("iter", "")
        body_lines = [emit_python_code(child, indent + 1) for child in ast.children]
        if not body_lines:
            body_lines = [f"{ind}    pass"]
        body = "\n".join(body_lines)
        return f"{ind}for {target} in {iterable}:\n{body}"
    return ""


def emit_latex_code(ast: UASTNode) -> str:
    if ast.node_type == "function":
        params = ",~".join(ast.meta.get("params", []))
        body = "\\\n".join(filter(None, (emit_latex_code(child) for child in ast.children)))
        return (
            "\\documentclass{article}\\n\\begin{document}\\n"
            f"\\textbf{{def}}~{ast.name}({params}):\\\n{body}\\n"
            "\\end{document}"
        )
    elif ast.node_type == "call":
        args = ",~".join(str(arg).replace(" ", "~") for arg in ast.meta.get("args", []))
        return f"\\texttt{{{ast.name}({args})}}"
    elif ast.node_type == "assign":
        target = str(ast.meta.get("target", "")).replace(" ", "~")
        value = str(ast.meta.get("value", "")).replace(" ", "~")
        return f"\\texttt{{{target}~=~{value}}}"
    elif ast.node_type == "return":
        value = str(ast.meta.get("value", "")).replace(" ", "~")
        return f"\\texttt{{return~{value}}}"
    elif ast.node_type == "if":
        cond = str(ast.meta.get("condition", "")).replace(" ", "~")
        body = "\\\n".join(filter(None, (emit_latex_code(child) for child in ast.children)))
        orelse_children = ast.meta.get("orelse", [])
        if orelse_children:
            else_body = "\\\n".join(
                filter(None, (emit_latex_code(child) for child in orelse_children))
            )
            return f"\\texttt{{if~{cond}:}}\\\n{body}\\\n\\texttt{{else:}}\\\n{else_body}"
        return f"\\texttt{{if~{cond}:}}\\\n{body}"
    elif ast.node_type == "while":
        cond = str(ast.meta.get("condition", "")).replace(" ", "~")
        body = "\\\n".join(filter(None, (emit_latex_code(child) for child in ast.children)))
        return f"\\texttt{{while~{cond}:}}\\\n{body}"
    elif ast.node_type == "for":
        target = str(ast.meta.get("target", "")).replace(" ", "~")
        iterable = str(ast.meta.get("iter", "")).replace(" ", "~")
        body = "\\\n".join(filter(None, (emit_latex_code(child) for child in ast.children)))
        return f"\\texttt{{for~{target}~in~{iterable}:}}\\\n{body}"
    return ""


def emit_cpp_code(ast: UASTNode) -> str:
    ind = "    "

    def emit_cpp_node(node: UASTNode, depth: int = 1) -> str:
        prefix = ind * depth
        if node.node_type == "call":
            args = ", ".join(str(arg) for arg in node.meta.get("args", []))
            return f"{prefix}std::cout << {args} << std::endl;"
        if node.node_type == "assign":
            return f"{prefix}auto {node.meta.get('target', '')} = {node.meta.get('value', '')};"
        if node.node_type == "return":
            return f"{prefix}return {node.meta.get('value', '')};"
        if node.node_type == "if":
            cond = node.meta.get("condition", "")
            body_lines = [emit_cpp_node(child, depth + 1) for child in node.children]
            body = "\n".join(body_lines) or f"{prefix}    // no-op"
            orelse_children = node.meta.get("orelse", [])
            if orelse_children:
                else_body = "\n".join(emit_cpp_node(child, depth + 1) for child in orelse_children)
                else_body = else_body or f"{prefix}    // no-op"
                return f"{prefix}if ({cond}) {{\n{body}\n{prefix}}} else {{\n{else_body}\n{prefix}}}"
            return f"{prefix}if ({cond}) {{\n{body}\n{prefix}}}"
        if node.node_type == "while":
            cond = node.meta.get("condition", "")
            body_lines = [emit_cpp_node(child, depth + 1) for child in node.children]
            body = "\n".join(body_lines) or f"{prefix}    // no-op"
            return f"{prefix}while ({cond}) {{\n{body}\n{prefix}}}"
        if node.node_type == "for":
            target = node.meta.get("target", "")
            iterable = node.meta.get("iter", "")
            body_lines = [emit_cpp_node(child, depth + 1) for child in node.children]
            body = "\n".join(body_lines) or f"{prefix}    // no-op"
            return f"{prefix}for (auto {target} : {iterable}) {{\n{body}\n{prefix}}}"
        return f"{prefix}// unknown node"

    if ast.node_type == "function":
        params = ", ".join(f"int {p}" for p in ast.meta.get("params", []))
        body_lines = [emit_cpp_node(child, 1) for child in ast.children]
        body = "\n".join(body_lines) or f"{ind}// TODO: implement"
        func = f"void {ast.name}({params}) {{\n{body}\n}}"
        main_body = "    // Entry point\n    return 0;"
        return "#include <iostream>\n\n" + func + "\n\nint main() {\n" + main_body + "\n}"
    return ""


def emit_js_code(ast: UASTNode) -> str:
    ind = "    "

    def emit_js_node(node: UASTNode, depth: int = 1) -> str:
        prefix = ind * depth
        if node.node_type == "call":
            args = ", ".join(str(arg) for arg in node.meta.get("args", []))
            return f"{prefix}console.log({args});"
        if node.node_type == "assign":
            return f"{prefix}let {node.meta.get('target', '')} = {node.meta.get('value', '')};"
        if node.node_type == "return":
            return f"{prefix}return {node.meta.get('value', '')};"
        if node.node_type == "if":
            cond = node.meta.get("condition", "")
            body_lines = [emit_js_node(child, depth + 1) for child in node.children]
            body = "\n".join(body_lines) or f"{prefix}    // no-op"
            orelse_children = node.meta.get("orelse", [])
            if orelse_children:
                else_body = "\n".join(emit_js_node(child, depth + 1) for child in orelse_children)
                else_body = else_body or f"{prefix}    // no-op"
                return f"{prefix}if ({cond}) {{\n{body}\n{prefix}}} else {{\n{else_body}\n{prefix}}}"
            return f"{prefix}if ({cond}) {{\n{body}\n{prefix}}}"
        if node.node_type == "while":
            cond = node.meta.get("condition", "")
            body_lines = [emit_js_node(child, depth + 1) for child in node.children]
            body = "\n".join(body_lines) or f"{prefix}    // no-op"
            return f"{prefix}while ({cond}) {{\n{body}\n{prefix}}}"
        if node.node_type == "for":
            target = node.meta.get("target", "")
            iterable = node.meta.get("iter", "")
            body_lines = [emit_js_node(child, depth + 1) for child in node.children]
            body = "\n".join(body_lines) or f"{prefix}    // no-op"
            return f"{prefix}for (const {target} of {iterable}) {{\n{body}\n{prefix}}}"
        return f"{prefix}// unknown node"

    if ast.node_type == "function":
        params = ", ".join(ast.meta.get("params", []))
        body_lines = [emit_js_node(child, 1) for child in ast.children]
        body = "\n".join(body_lines)
        if not body:
            body = f"{ind}// TODO: implement"
        func = f"function {ast.name}({params}) {{\n{body}\n}}"
        return func + "\n\n// Entry point placeholder\n" + f"// {ast.name}();"
    return ""


def emit_rust_code(ast: UASTNode) -> str:
    ind = "    "

    def emit_rust_node(node: UASTNode, depth: int = 1) -> str:
        prefix = ind * depth
        if node.node_type == "call":
            args_list = [str(arg) for arg in node.meta.get("args", [])]
            if args_list:
                placeholders = ", ".join(["{:?}"] * len(args_list))
                args = ", ".join(args_list)
                return f"{prefix}println!(\"{placeholders}\", {args});"
            return f"{prefix}println!(\"\");"
        if node.node_type == "assign":
            return f"{prefix}let mut {node.meta.get('target', '')} = {node.meta.get('value', '')};"
        if node.node_type == "return":
            return f"{prefix}return {node.meta.get('value', '')};"
        if node.node_type == "if":
            cond = node.meta.get("condition", "")
            body_lines = [emit_rust_node(child, depth + 1) for child in node.children]
            body = "\n".join(body_lines) or f"{prefix}    // no-op"
            orelse_children = node.meta.get("orelse", [])
            if orelse_children:
                else_body = "\n".join(emit_rust_node(child, depth + 1) for child in orelse_children)
                else_body = else_body or f"{prefix}    // no-op"
                return f"{prefix}if {cond} {{\n{body}\n{prefix}}} else {{\n{else_body}\n{prefix}}}"
            return f"{prefix}if {cond} {{\n{body}\n{prefix}}}"
        if node.node_type == "while":
            cond = node.meta.get("condition", "")
            body_lines = [emit_rust_node(child, depth + 1) for child in node.children]
            body = "\n".join(body_lines) or f"{prefix}    // no-op"
            return f"{prefix}while {cond} {{\n{body}\n{prefix}}}"
        if node.node_type == "for":
            target = node.meta.get("target", "")
            iterable = node.meta.get("iter", "")
            body_lines = [emit_rust_node(child, depth + 1) for child in node.children]
            body = "\n".join(body_lines) or f"{prefix}    // no-op"
            return f"{prefix}for {target} in {iterable} {{\n{body}\n{prefix}}}"
        return f"{prefix}// unknown node"

    if ast.node_type == "function":
        params = ", ".join(f"{p}: impl std::fmt::Debug" for p in ast.meta.get("params", []))
        body_lines = [emit_rust_node(child, 1) for child in ast.children]
        body = "\n".join(body_lines) or f"{ind}// TODO: implement"
        func = f"fn {ast.name}({params}) {{\n{body}\n}}"
        main_body = "    // Entry point\n}"
        return func + "\n\nfn main() {\n" + main_body
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
        "JavaScript": emit_js_code(uast),
        "Rust": emit_rust_code(uast)
    }

    save_output_files(languages)

    validators = {
        "Python": lambda code: validate_code(["python3", "-m", "py_compile"], code, ".py"),
        "LaTeX": lambda code: validate_code(["pdflatex", "-interaction=nonstopmode"], code, ".tex"),
        "C++": lambda code: validate_code(["g++", "-o", "/dev/null"], code, ".cpp"),
        "JavaScript": lambda code: validate_code(["node", "--check"], code, ".js"),
        "Rust": lambda code: validate_code(["rustc", "-o", "/dev/null"], code, ".rs")
    }

    print("\n--- Window Validation ---")
    for lang, code in languages.items():
        if validators[lang](code):
            print(f"✅ {lang} window stands.")
        else:
            print(f"💥 {lang} window shattered.")
