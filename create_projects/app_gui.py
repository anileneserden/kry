import os
import json

GUI_MAIN_C_TEMPLATE = """#include "kef2_api.h"

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

DEFAULT_KEF2_API_H = """#ifndef KEF2_API_H
#define KEF2_API_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#define ANCHOR_LEFT   (1 << 0)
#define ANCHOR_RIGHT  (1 << 1)
#define ANCHOR_TOP    (1 << 2)
#define ANCHOR_BOTTOM (1 << 3)

typedef struct __attribute__((packed)) {
    char name[32];
    uint32_t size;
    bool is_directory;
} vfs_file_info_t;

// KEFv2 API Tablosu ve Yardımcı Fonksiyon Makroları
#define KEF_API_TABLE ((struct kef_api_table_t*)0x501000)

struct kef_api_table_t {
    int (*window_create)(const char* title, int width, int height);
    void (*print)(const char* str);
    void (*exit)(void);
    int (*label_create)(int x, int y, uint32_t color, const char* text, uint8_t anchor);
    int (*panel_create)(int x, int y, int w, int h, uint32_t color, uint32_t hover_color, void (*on_click)(void), void (*on_hover)(void), uint8_t anchor);
    int (*button_create)(int x, int y, int w, int h, uint32_t bg_color, uint32_t text_color, const char* text, void (*on_click)(void), uint8_t anchor);
    int (*input_create)(int x, int y, int w, int h, 
                        const char* text, const char* placeholdertext, 
                        uint32_t backcolor, uint32_t color, 
                        uint32_t placeholder_color, uint32_t border_color, 
                        int border_thickness, uint8_t anchor);
    int (*input_get_text)(int input_id, char* out_buf, int max_len);
    int (*combobox_create)(int x, int y, int w, int h, const char** items, int item_count, int default_index, uint32_t bg_color, uint32_t text_color, uint32_t border_color, uint8_t anchor);
    int (*get_directory_files)(const char* full_path, void* out_list, int max_count);
    void* (*read_file)(const char* full_path, uint32_t* out_size);
    int (*strcmp)(const char* s1, const char* s2);
    size_t (*strlen)(const char* str);
    void (*yield)(void);
    uint32_t* (*canvas_create)(int x, int y, int w, int h, uint8_t anchor, int* out_canvas_id);
    void (*canvas_update_buffer)(int canvas_id);
    void (*background_color)(uint32_t color);
    void (*reboot_system)(void);
    void (*shutdown_system)(void);
    bool (*is_key_pressed)(int key_code);
};

// Inline sarmalayıcılar (Wrapper macros)
static inline int kef_window_create(const char* t, int w, int h) { return KEF_API_TABLE->window_create(t, w, h); }
static inline void kef_print(const char* s) { KEF_API_TABLE->print(s); }
static inline int label(int x, int y, uint32_t c, const char* t, uint8_t a) { return KEF_API_TABLE->label_create(x, y, c, t, a); }
static inline int panel(int x, int y, int w, int h, uint32_t c, uint8_t a) { return KEF_API_TABLE->panel_create(x, y, w, h, c, c, 0, 0, a); }
static inline int kef_get_directory_files(const char* path, void* list, int max) { return KEF_API_TABLE->get_directory_files(path, list, max); }
static inline void* kef_read_file(const char* path, uint32_t* size) { return KEF_API_TABLE->read_file(path, size); }

#endif
"""

KEF2_FORMAT_PY_TEMPLATE = """#!/usr/bin/env python3
import sys
import struct
import subprocess
import os

def format_kef2(input_bin, output_kef, input_elf):
    MAGIC = 0x3246454B  # "KEF2" ascii
    VERSION = 2
    
    if not os.path.exists(input_bin):
        print(f"[-] Hata: Input binary dosyası bulunamadı: {input_bin}")
        sys.exit(1)
        
    if not os.path.exists(input_elf):
        print(f"[-] Hata: Input ELF dosyası bulunamadı: {input_elf}")
        sys.exit(1)

    with open(input_bin, "rb") as f:
        payload = f.read()
        
    payload_size = len(payload)
    
    # KEFv2 Header: Magic (4B), Version (2B), Section Count (2B)
    HEADER_FORMAT = "<IHH"
    header_size = struct.calcsize(HEADER_FORMAT)
    
    # KEFv2 Section Header: Type (4B), Offset (4B), Size (4B)
    SECTION_HEADER_FORMAT = "<III"
    section_header_size = struct.calcsize(SECTION_HEADER_FORMAT)
    
    section_count = 1
    text_section_offset = header_size + (section_count * section_header_size)
    
    header = struct.pack(HEADER_FORMAT, MAGIC, VERSION, section_count)
    
    # KEF2_SECTION_TEXT = 1
    KEF2_SECTION_TEXT = 1
    sec_header = struct.pack(SECTION_HEADER_FORMAT, KEF2_SECTION_TEXT, text_section_offset, payload_size)
    
    print(f"[+] İşlenen Binary: {input_bin}")
    print(f"[+] KEFv2 Paketleme: Section Count = {section_count}, Payload Boyutu = {payload_size} bytes")
    
    with open(output_kef, "wb") as f:
        f.write(header)
        f.write(sec_header)
        f.write(payload)
        
    print(f"[+] Başarıyla KEFv2 formatında paketlendi: {output_kef}\\n")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Kullanım: python3 kef2_format.py <input.bin> <output.kef> <input.elf>")
        sys.exit(1)
        
    format_kef2(sys.argv[1], sys.argv[2], sys.argv[3])
"""

def ensure_kry_sdk():
    """~/.kry/ altında include/kef2_api.h, linker.ld ve kef2_format.py varlığını kontrol eder, yoksa oluşturur."""
    kry_home = os.path.expanduser("~/.kry")
    kry_include = os.path.join(kry_home, "include")
    api_header_path = os.path.join(kry_include, "kef2_api.h")
    linker_path = os.path.join(kry_home, "linker.ld")
    kef_format_py_path = os.path.join(kry_home, "kef2_format.py")
    
    os.makedirs(kry_include, exist_ok=True)
    
    if not os.path.exists(api_header_path):
        print(f"[*] '{api_header_path}' bulunamadı. Otomatik olarak oluşturuluyor...")
        with open(api_header_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_KEF2_API_H)
        print(f"[✔] Varsayılan SDK dosyası oluşturuldu: {api_header_path}")
        
    if not os.path.exists(linker_path):
        print(f"[*] '{linker_path}' bulunamadı. Otomatik olarak oluşturuluyor...")
        with open(linker_path, "w", encoding="utf-8") as f:
            f.write(LINKER_LD_TEMPLATE)
        print(f"[✔] Varsayılan linker betiği oluşturuldu: {linker_path}")
        
    if not os.path.exists(kef_format_py_path):
        print(f"[*] '{kef_format_py_path}' bulunamadı. Otomatik olarak oluşturuluyor...")
        with open(kef_format_py_path, "w", encoding="utf-8") as f:
            f.write(KEF2_FORMAT_PY_TEMPLATE)
        print(f"[✔] Varsayılan paketleme betiği oluşturuldu: {kef_format_py_path}")

def create_app(args):
    target_dir = args.dir if args.dir else "."
    app_name = args.name
    
    ensure_kry_sdk()
    kry_home = os.path.expanduser("~/.kry")
    kry_include = os.path.join(kry_home, "include")
    global_linker_path = os.path.join(kry_home, "linker.ld")

    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
        print(f"[+] Dizin oluşturuldu: {target_dir}")

    # 1. kry.json oluşturma
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
            "-m", "elf_i386", "-T", global_linker_path, "--oformat", "binary"
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

    # 3. VS Code c_cpp_properties.json desteği
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

    print(f"\n[+] {app_name} projesi {target_dir} içinde KEFv2 desteğiyle hazırlandı!")