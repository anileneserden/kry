import os
import json

GUI_MAIN_C_TEMPLATE = """#include "kef_api.h"

int main(void) {
    kef_print("{app_name} baslatiliyor...\\n");
    
    // Pencereyi Oluştur
    kef_window_create("{app_name}", 400, 250);
    
    // Başlık ve Etiket
    label(30, 40, 0xFFFFFFFF, "KryonOS C GUI Uygulamasi", ANCHOR_LEFT);

    // Örnek Panel ve Durum Alanı
    panel(30, 80, 340, 50, 0xFF2A2A2A, ANCHOR_LEFT | ANCHOR_RIGHT);
    label(45, 97, 0xFFAAAAAA, "Durum: Sistem stabil calisiyor.", ANCHOR_LEFT);

    // Alt Durum Çubuğu
    panel(20, 200, 360, 30, 0xFF222222, ANCHOR_LEFT | ANCHOR_RIGHT | ANCHOR_BOTTOM);
    label(30, 210, 0xFFAAAAAA, "Hazir", ANCHOR_LEFT | ANCHOR_BOTTOM);

    return 0;
}

__attribute__((section(".text._start"), naked)) void _start(void) {
    __asm__ volatile (
        "call main\\n\\t"
        "ret\\n\\t"
    );
}
"""

LINKER_LD_TEMPLATE = """ENTRY(_start)
OUTPUT_FORMAT(elf32-i386)

SECTIONS
{
    . = 0x400000;

    .text : {
        *(.text._start)
        *(.text*)
    }

    .rodata : {
        *(.rodata*)
    }

    .data : {
        *(.data*)
    }

    .bss : {
        *(.bss*)
        *(COMMON)
    }
}
"""

def create_app(args):
    target_dir = args.dir if args.dir else "."
    app_name = args.name
    
    kry_include = os.path.expanduser("~/.kry/include")
    if not os.path.exists(kry_include):
        print(f"[-] Uyarı: '{kry_include}' bulunamadı! Lütfen kef_api.h dosyasının orada olduğundan emin olun.")

    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
        print(f"[+] Dizin oluşturuldu: {target_dir}")

    # 1. kry.json oluşturma (Derleme parametreleri artık burada saklanıyor)
    kry_json_path = os.path.join(target_dir, "kry.json")
    kry_config = {
        "name": app_name,
        "author": getattr(args, "author", "Kuvix Developer"),
        "version": getattr(args, "version", "1.0.0"),
        "type": "c-app",
        "source": "main.c",
        "compiler": "gcc",
        "c-flags": [
            "-m32", "-ffreestanding", "-fno-pie", "-fno-stack-protector",
            "-nostdlib", "-I~/.kry/include", "-O2"
        ],
        "linker-flags": [
            "-m", "elf_i386", "-T", "linker.ld", "--oformat", "binary"
        ]
    }
    with open(kry_json_path, "w", encoding="utf-8") as f:
        json.dump(kry_config, f, indent=4)
    print(f"[+] {kry_json_path} oluşturuldu.")

    # 2. main.c oluşturma
    main_c_path = os.path.join(target_dir, "main.c")
    with open(main_c_path, "w", encoding="utf-8") as f:
        f.write(GUI_MAIN_C_TEMPLATE.replace("{app_name}", app_name))
    print(f"[+] {main_c_path} oluşturuldu.")

    # 3. linker.ld oluşturma
    linker_path = os.path.join(target_dir, "linker.ld")
    with open(linker_path, "w", encoding="utf-8") as f:
        f.write(LINKER_LD_TEMPLATE)
    print(f"[+] {linker_path} oluşturuldu.")

    # 4. VS Code c_cpp_properties.json desteği
    editor_choice = getattr(args, 'editor', 'vscode')
    if editor_choice == "vscode":
        vscode_dir = os.path.join(target_dir, ".vscode")
        os.makedirs(vscode_dir, exist_ok=True)
        cpp_props_path = os.path.join(vscode_dir, "c_cpp_properties.json")
        cpp_config = {
            "configurations": [
                {
                    "name": "KryonOS C",
                    "includePath": ["${workspaceFolder}/**", kry_include],
                    "compilerPath": "/usr/bin/gcc",
                    "cStandard": "c11",
                    "cppStandard": "c++17",
                    "intelliSenseMode": "linux-gcc-x86"
                }
            ],
            "version": 4
        }
        with open(cpp_props_path, "w", encoding="utf-8") as f:
            json.dump(cpp_config, f, indent=4)
        print(f"[+] {cpp_props_path} oluşturuldu.")

    print(f"\nBaşarıyla Makefile içermeyen '{app_name}' projesi {target_dir} içinde hazırlandı!")