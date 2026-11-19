import ast
import json
import os
import shutil
import subprocess
import sys

# Python `from lex2 import ...` sembollerinin C karşılıkları
LEX2_SYMBOL_MAP = {
    # Sabitler
    "ANCHOR_LEFT": "ANCHOR_LEFT",
    "ANCHOR_RIGHT": "ANCHOR_RIGHT",
    "ANCHOR_TOP": "ANCHOR_TOP",
    "ANCHOR_BOTTOM": "ANCHOR_BOTTOM",
    "SIZE_MODE_NORMAL": "SIZE_MODE_NORMAL",
    "SIZE_MODE_STRETCH": "SIZE_MODE_STRETCH",
    "SIZE_MODE_FIT": "SIZE_MODE_FIT",
    # Doğrudan çağrılar
    "window_create": "lex_window_create",
    "window_create_with_tabs": "lex_window_create_with_tabs",
    "print_log": "lex_print",
    "exit_app": "lex_exit",
    "label": "label",
    "panel": "panel",
    "panel_ex": "panel_ex",
    "button": "button",
    "picturebox": "picturebox",
    "input_create": "input_create",
    "input_set_text": "input_set_text",
    "background_color": "background_color",
    "browser_create": "browser_create",
    "browser_load_html": "browser_load_html",
    "yield_cpu": "yield",
}

START_ASM_BLOCK = """__attribute__((section(".text._start"), naked)) void _start(void) {
    __asm__ volatile (
        "call main\\n\\t"
        "ret\\n\\t"
    );
}
"""


class _PyToCTranspiler:
    def __init__(self, filename: str):
        self.filename = filename
        self.imported_lex2: dict[str, str] = {}
        self.temp_counter = 0

    def _fresh_name(self, prefix: str) -> str:
        self.temp_counter += 1
        return f"_lnr_{prefix}_{self.temp_counter}"

    def _err(self, node: ast.AST, msg: str) -> None:
        line = getattr(node, "lineno", "?")
        col = getattr(node, "col_offset", "?")
        print(f"[-] Transpile hatasi ({self.filename}:{line}:{col}): {msg}")
        sys.exit(1)

    def _escape_c_str(self, s: str) -> str:
        return (
            s.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )

    def _infer_c_type(self, expr: ast.AST) -> str:
        if isinstance(expr, ast.Constant):
            if isinstance(expr.value, bool):
                return "bool"
            if isinstance(expr.value, int):
                return "uint32_t" if expr.value > 0x7FFFFFFF else "int"
            if isinstance(expr.value, str):
                return "const char*"
        if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.USub):
            return "int"
        if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name):
            if expr.func.id == "read_file":
                return "char*"
            if expr.func.id == "input_get_text":
                return "const char*"
        return "int"

    def _emit_expr(self, expr: ast.AST, pre_stmts: list[str]) -> str:
        if isinstance(expr, ast.Constant):
            if isinstance(expr.value, bool):
                return "true" if expr.value else "false"
            if isinstance(expr.value, int):
                return hex(expr.value) if expr.value >= 0x10000 else str(expr.value)
            if isinstance(expr.value, str):
                return f'"{self._escape_c_str(expr.value)}"'
            self._err(expr, f"Desteklenmeyen sabit deger: {type(expr.value).__name__}")

        if isinstance(expr, ast.Name):
            if expr.id in self.imported_lex2:
                return self.imported_lex2[expr.id]
            return expr.id

        if isinstance(expr, ast.UnaryOp):
            operand = self._emit_expr(expr.operand, pre_stmts)
            if isinstance(expr.op, ast.USub):
                return f"-({operand})"
            if isinstance(expr.op, ast.Not):
                return f"!({operand})"
            self._err(expr, f"Desteklenmeyen tekli operator: {type(expr.op).__name__}")

        if isinstance(expr, ast.BinOp):
            left = self._emit_expr(expr.left, pre_stmts)
            right = self._emit_expr(expr.right, pre_stmts)
            op_map = {
                ast.Add: "+",
                ast.Sub: "-",
                ast.Mult: "*",
                ast.Div: "/",
                ast.BitOr: "|",
                ast.BitAnd: "&",
                ast.BitXor: "^",
                ast.LShift: "<<",
                ast.RShift: ">>",
            }
            c_op = op_map.get(type(expr.op))
            if not c_op:
                self._err(expr, f"Desteklenmeyen ikili operator: {type(expr.op).__name__}")
            return f"({left} {c_op} {right})"

        if isinstance(expr, ast.Compare):
            if len(expr.ops) != 1 or len(expr.comparators) != 1:
                self._err(expr, "Zincirleme karsilastirmalar henuz desteklenmiyor.")
            left = self._emit_expr(expr.left, pre_stmts)
            right = self._emit_expr(expr.comparators[0], pre_stmts)
            op = expr.ops[0]
            if isinstance(op, ast.Eq):
                return f"({left} == {right})"
            if isinstance(op, ast.NotEq):
                return f"({left} != {right})"
            if isinstance(op, ast.Lt):
                return f"({left} < {right})"
            if isinstance(op, ast.LtE):
                return f"({left} <= {right})"
            if isinstance(op, ast.Gt):
                return f"({left} > {right})"
            if isinstance(op, ast.GtE):
                return f"({left} >= {right})"
            self._err(expr, f"Desteklenmeyen karsilastirma operatoru: {type(op).__name__}")

        if isinstance(expr, ast.Call):
            if not isinstance(expr.func, ast.Name):
                self._err(expr, "Yalnizca dogrudan fonksiyon cagrilari destekleniyor.")
            fn_name = expr.func.id

            if fn_name in self.imported_lex2 and self.imported_lex2[fn_name] is None:
                self._err(expr, f"'{fn_name}' bir sabit, fonksiyon degil.")

            if fn_name == "input_get_text":
                if len(expr.args) != 1:
                    self._err(expr, "input_get_text(input_id) tam 1 arguman alir.")
                inp_id = self._emit_expr(expr.args[0], pre_stmts)
                buf_name = self._fresh_name("buf")
                pre_stmts.append(f"char {buf_name}[256] = {{0}};")
                pre_stmts.append(f"input_get_text({inp_id}, {buf_name}, sizeof({buf_name}));")
                return buf_name

            if fn_name == "read_file":
                if len(expr.args) != 1:
                    self._err(expr, "read_file(path) tam 1 arguman alir.")
                path_expr = self._emit_expr(expr.args[0], pre_stmts)
                sz_name = self._fresh_name("sz")
                data_name = self._fresh_name("data")
                pre_stmts.append(f"uint32_t {sz_name} = 0;")
                pre_stmts.append(f"char* {data_name} = (char*)lex_read_file({path_expr}, &{sz_name});")
                return data_name

            c_fn = self.imported_lex2.get(fn_name, fn_name)
            args_c = [self._emit_expr(a, pre_stmts) for a in expr.args]
            return f"{c_fn}({', '.join(args_c)})"

        self._err(expr, f"Desteklenmeyen ifade: {type(expr).__name__}")
        return ""

    def _emit_stmt(self, stmt: ast.stmt, indent: str, declared_locals: set[str], is_main: bool) -> list[str]:
        lines: list[str] = []
        pre: list[str] = []

        if isinstance(stmt, ast.Global):
            return []

        if isinstance(stmt, ast.Pass):
            return [f"{indent}/* pass */"]

        if isinstance(stmt, ast.Return):
            if stmt.value is None:
                val = "0" if is_main else ""
                lines.append(f"{indent}return {val};".strip())
            else:
                expr_c = self._emit_expr(stmt.value, pre)
                lines.extend(f"{indent}{p}" for p in pre)
                lines.append(f"{indent}return {expr_c};")
            return lines

        if isinstance(stmt, ast.Expr):
            expr_c = self._emit_expr(stmt.value, pre)
            lines.extend(f"{indent}{p}" for p in pre)
            lines.append(f"{indent}{expr_c};")
            return lines

        if isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                self._err(stmt, "Yalnizca tek degiskene atama destekleniyor.")
            target = stmt.targets[0].id
            val_c = self._emit_expr(stmt.value, pre)
            lines.extend(f"{indent}{p}" for p in pre)
            if target not in declared_locals:
                c_type = self._infer_c_type(stmt.value)
                declared_locals.add(target)
                lines.append(f"{indent}{c_type} {target} = {val_c};")
            else:
                lines.append(f"{indent}{target} = {val_c};")
            return lines

        if isinstance(stmt, ast.If):
            cond_c = self._emit_expr(stmt.test, pre)
            lines.extend(f"{indent}{p}" for p in pre)
            lines.append(f"{indent}if ({cond_c}) {{")
            for sub in stmt.body:
                lines.extend(self._emit_stmt(sub, indent + "    ", declared_locals.copy(), is_main))
            if stmt.orelse:
                if len(stmt.orelse) == 1 and isinstance(stmt.orelse[0], ast.If):
                    lines.append(f"{indent}}} else ")
                    elif_lines = self._emit_stmt(stmt.orelse[0], indent, declared_locals.copy(), is_main)
                    if elif_lines:
                        elif_lines[0] = elif_lines[0].lstrip()
                    lines.extend(elif_lines)
                else:
                    lines.append(f"{indent}}} else {{")
                    for sub in stmt.orelse:
                        lines.extend(self._emit_stmt(sub, indent + "    ", declared_locals.copy(), is_main))
                    lines.append(f"{indent}}}")
            else:
                lines.append(f"{indent}}}")
            return lines

        self._err(stmt, f"Desteklenmeyen Python ifadesi: {type(stmt).__name__}")
        return lines

    def transpile(self, source: str) -> str:
        try:
            tree = ast.parse(source, filename=self.filename)
        except SyntaxError as e:
            print(f"[-] Python soz dizimi hatasi ({self.filename}:{e.lineno}): {e.msg}")
            sys.exit(1)

        globals_c: list[str] = []
        funcs_c: list[str] = []
        main_fn: ast.FunctionDef | None = None

        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                if node.module != "lex2":
                    self._err(node, f"Desteklenmeyen modul: '{node.module}'. Yalnizca 'lex2' destekleniyor.")
                for alias in node.names:
                    if alias.name not in LEX2_SYMBOL_MAP:
                        self._err(node, f"'lex2' icinde '{alias.name}' bulunamadi.")
                    local_name = alias.asname or alias.name
                    self.imported_lex2[local_name] = LEX2_SYMBOL_MAP[alias.name]

            elif isinstance(node, ast.Assign):
                if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                    self._err(node, "Global kapsamda yalnizca basit degisken atamalari destekleniyor.")
                name = node.targets[0].id
                c_type = self._infer_c_type(node.value)
                pre: list[str] = []
                val_c = self._emit_expr(node.value, pre)
                for p in pre:
                    globals_c.append(f"static {p}")
                globals_c.append(f"static {c_type} {name} = {val_c};")

            elif isinstance(node, ast.FunctionDef):
                if node.args.args:
                    self._err(node, "Simdilik parametresiz fonksiyonlar destekleniyor.")
                if node.name == "main":
                    main_fn = node
                else:
                    body_lines: list[str] = []
                    for sub in node.body:
                        body_lines.extend(self._emit_stmt(sub, "    ", set(), is_main=False))
                    funcs_c.append(f"static void {node.name}(void) {{\n" + "\n".join(body_lines) + "\n}\n")

            else:
                self._err(node, f"Ust duzeyde desteklenmeyen yapi: {type(node).__name__}")

        if main_fn is None:
            print(f"[-] Transpile hatasi ({self.filename}): 'def main():' fonksiyonu bulunamadi.")
            sys.exit(1)

        main_lines: list[str] = []
        for sub in main_fn.body:
            main_lines.extend(self._emit_stmt(sub, "    ", set(), is_main=True))
        if not main_lines or not main_lines[-1].strip().startswith("return "):
            main_lines.append("    return 0;")

        out_parts = [
            '#include "lex2_api.h"',
            "",
        ]
        if globals_c:
            out_parts.extend(globals_c)
            out_parts.append("")
        if funcs_c:
            out_parts.extend(funcs_c)
        out_parts.append("int main(void) {\n" + "\n".join(main_lines) + "\n}\n")
        out_parts.append(START_ASM_BLOCK)
        return "\n".join(out_parts)


def transpile_python_to_c(py_path: str, out_c_path: str) -> None:
    with open(py_path, "r", encoding="utf-8") as f:
        py_source = f.read()
    transpiler = _PyToCTranspiler(py_path)
    c_code = transpiler.transpile(py_source)
    with open(out_c_path, "w", encoding="utf-8") as f:
        f.write(c_code)


def ensure_lnr_sdk_on_build():
    """~/.lnr/ altında include/lex2_api.h, linker.ld ve lex2_format.py dosyalarının varlığını kontrol eder."""
    lnr_home = os.path.expanduser("~/.lnr")
    lnr_include = os.path.join(lnr_home, "include")
    api_header_path = os.path.join(lnr_include, "lex2_api.h")
    linker_path = os.path.join(lnr_home, "linker.ld")
    lex_format_py_path = os.path.join(lnr_home, "lex2_format.py")

    os.makedirs(lnr_include, exist_ok=True)

    need_write_api = True
    if os.path.exists(api_header_path):
        with open(api_header_path, "r", encoding="utf-8") as f:
            content = f.read()
            if (
                "vfs_file_info_t" in content
                and "LEX2_API_H" in content
                and "picturebox_create" in content
                and "browser_create" in content
                and "input_set_text" in content
            ):
                need_write_api = False

    if need_write_api:
        print(f"[*] Bilgi: '{api_header_path}' eksik veya güncel değil. Otomatik güncelleniyor...")
        with open(api_header_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_LEX2_API_H)
        print("[✔] LEXv2 SDK başlık dosyası güncellendi.")

    if not os.path.exists(linker_path):
        print(f"[*] Bilgi: '{linker_path}' bulunamadı. Oluşturuluyor...")
        with open(linker_path, "w", encoding="utf-8") as f:
            f.write(LINKER_LD_TEMPLATE)
        print("[✔] Merkezi linker betiği oluşturuldu.")

    if not os.path.exists(lex_format_py_path):
        print(f"[*] Bilgi: '{lex_format_py_path}' bulunamadı. Oluşturuluyor...")
        with open(lex_format_py_path, "w", encoding="utf-8") as f:
            f.write(LEX2_FORMAT_PY_TEMPLATE)
        print("[✔] LEXv2 paketleme betiği oluşturuldu.")


def build_app(args):
    print("[*] LenorOS uygulaması LEXv2 formatında derleniyor...")

    target_dir = args.dir if hasattr(args, "dir") and args.dir else "."
    if not os.path.exists(target_dir):
        print(f"[-] Hata: Hedef dizin bulunamadı: {target_dir}")
        sys.exit(1)

    # --- BURAYA EKLİYORUZ: Build aşamasında resources klasörü güvencesi ---
    res_check_dir = os.path.join(target_dir, "resources")
    os.makedirs(res_check_dir, exist_ok=True)
    # ------------------------------------------------------------------

    ensure_lnr_sdk_on_build()

    lnr_json_path = os.path.join(target_dir, "lnr.json")
    if not os.path.exists(lnr_json_path):
        print(f"[-] Hata: '{target_dir}' içinde 'lnr.json' konfigürasyon dosyası bulunamadı!")
        sys.exit(1)

    with open(lnr_json_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    app_name = config.get("name", "app")
    source_file = config.get("source", "main.c")
    compiler = config.get("compiler", "gcc")
    raw_c_flags = config.get("c-flags", [])
    linker_flags = config.get("linker-flags", [])

    c_flags = []
    for flag in raw_c_flags:
        if flag.startswith("-I"):
            path_part = flag[2:]
            expanded_path = os.path.expanduser(path_part)
            c_flags.append(f"-I{expanded_path}")
        else:
            c_flags.append(os.path.expanduser(flag))

    global_linker_path = os.path.expanduser("~/.lnr/linker.ld")

    processed_linker_flags = []
    use_next_as_linker = False
    for flag in linker_flags:
        if use_next_as_linker:
            processed_linker_flags.append(global_linker_path)
            use_next_as_linker = False
            continue
        if flag == "-T":
            processed_linker_flags.append("-T")
            use_next_as_linker = True
            continue
        processed_linker_flags.append(os.path.expanduser(flag))

    if "-T" not in processed_linker_flags:
        processed_linker_flags.extend(["-T", global_linker_path])

    pure_linker_flags = []
    skip_next = False
    for flag in processed_linker_flags:
        if skip_base := (flag in ["--oformat", "-oformat"]):
            skip_next = True
            continue
        if skip_next:
            skip_next = False
            continue
        pure_linker_flags.append(flag)

    source_path = os.path.join(target_dir, source_file)
    if not os.path.exists(source_path):
        print(f"[-] Hata: Kaynak dosya bulunamadı: {source_path}")
        sys.exit(1)

    build_dir = os.path.join(target_dir, "build")
    clean_build = getattr(args, "clean", False)
    if clean_build and os.path.exists(build_dir):
        print(f"[*] Temizleniyor (-c): {build_dir} siliniyor...")
        shutil.rmtree(build_dir)

    os.makedirs(build_dir, exist_ok=True)

    is_python_source = source_path.endswith(".py") or config.get("type") == "py-app"
    if is_python_source:
        generated_c_path = os.path.join(build_dir, "main.generated.c")
        print("[*] Python uygulaması derleniyor...")
        transpile_python_to_c(source_path, generated_c_path)
        source_path = generated_c_path

    main_o = os.path.join(build_dir, "main.o")
    target_elf = os.path.join(build_dir, f"{app_name}.elf")
    target_bin = os.path.join(build_dir, f"{app_name}.bin")
    target_lex = os.path.join(target_dir, f"{app_name}.lex")

    format_script = os.path.expanduser("~/.lnr/lex2_format.py")

    try:
        print(f"[*] Çalıştırılıyor: {compiler} (C Derleme)")
        compile_cmd = [compiler] + c_flags + ["-c", source_path, "-o", main_o]
        subprocess.run(compile_cmd, check=True)

        print(f"[*] Çalıştırılıyor: ld (ELF Linkleme - Linker: {global_linker_path})")
        link_elf_cmd = ["ld"] + pure_linker_flags + [main_o, "-o", target_elf]
        subprocess.run(link_elf_cmd, cwd=target_dir, check=True)

        print("[*] Çalıştırılıyor: objcopy (Binary Çıkartma)")
        subprocess.run(["objcopy", "-O", "binary", target_elf, target_bin], check=True)

        print("[*] Çalıştırılıyor: lex2_format paketleme")
        if os.path.exists(format_script):
            pack_cmd = ["python3", format_script, target_bin, target_lex, target_elf]
            subprocess.run(pack_cmd, check=True)
        else:
            print(f"[-] Hata: '{format_script}' bulunamadı!")
            sys.exit(1)

        print(f"[+] Başarılı! Derlenen LEXv2: {target_lex}")

    except subprocess.CalledProcessError as e:
        print(f"[-] Derleme sırasında hata oluştu (Exit Code: {e.returncode}): {e}")
        sys.exit(1)