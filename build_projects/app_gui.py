import os
import subprocess
import sys
import shutil
import json

# SDK ve format betiği şablonları (Eğer silindiyse otomatik yeniden oluşturmak için)
DEFAULT_KEF_API_H = """#ifndef KEF_API_H
#define KEF_API_H

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
    
    // Kernel ile uyumlu olması için eklenen eksik pointer:
    int (*combobox_create)(int x, int y, int w, int h, const char** items, int item_count, int default_index, uint32_t bg_color, uint32_t text_color, uint32_t border_color, uint8_t anchor);

    int (*get_directory_files)(const char* full_path, vfs_file_info_t* out_list, int max_count);
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

// Inline Sarmalayıcılar (Wrappers)
static inline int kef_window_create(const char* t, int w, int h) { return KEF_API_TABLE->window_create(t, w, h); }
static inline void kef_print(const char* s) { KEF_API_TABLE->print(s); }
static inline void kef_exit(void) { KEF_API_TABLE->exit(); }

static inline int label(int x, int y, uint32_t c, const char* t, uint8_t a) { return KEF_API_TABLE->label_create(x, y, c, t, a); }
static inline int panel(int x, int y, int w, int h, uint32_t c, uint8_t a) { return KEF_API_TABLE->panel_create(x, y, w, h, c, c, 0, 0, a); }
static inline int kef_panel_create(int x, int y, int w, int h, uint32_t c, uint32_t hc, void (*click)(void), void (*hover)(void), uint8_t a) { 
    return KEF_API_TABLE->panel_create(x, y, w, h, c, hc, click, hover, a); 
}
static inline int button(int x, int y, int w, int h, uint32_t bg, uint32_t fg, const char* t, void (*click)(void), uint8_t a) { 
    return KEF_API_TABLE->button_create(x, y, w, h, bg, fg, t, click, a); 
}

static inline int kef_combobox_create(int x, int y, int w, int h, const char** items, int count, int def_idx, uint32_t bg, uint32_t fg, uint32_t border, uint8_t a) {
    return KEF_API_TABLE->combobox_create(x, y, w, h, items, count, def_idx, bg, fg, border, a);
}

static inline int kef_get_directory_files(const char* path, vfs_file_info_t* list, int max) { 
    return KEF_API_TABLE->get_directory_files(path, list, max); 
}
static inline void* kef_read_file(const char* path, uint32_t* size) { 
    return KEF_API_TABLE->read_file(path, size); 
}

static inline size_t kef_strlen(const char* str) { return KEF_API_TABLE->strlen(str); }
static inline int kef_strcmp(const char* s1, const char* s2) { return KEF_API_TABLE->strcmp(s1, s2); }

static inline void backgroundColor(uint32_t color) { KEF_API_TABLE->background_color(color); }
static inline void background_color(uint32_t color) { KEF_API_TABLE->background_color(color); }

static inline bool is_key_pressed(int key_code) { return KEF_API_TABLE->is_key_pressed(key_code); }

#endif
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

KEF_FORMAT_PY_TEMPLATE = """#!/usr/bin/env python3
import sys
import struct
import subprocess
import os

def get_symbol_offset(elf_file, symbol_name="_start"):
    try:
        result = subprocess.run(['nm', elf_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[2] == symbol_name:
                return int(parts[0], 16)
            elif len(parts) == 2 and parts[1] == symbol_name:
                return int(parts[0], 16)
    except Exception as e:
        print(f"[-] Sembol adresi alınamadı ({symbol_name}): {e}")
    return 0

def format_kef(input_bin, output_kef, input_elf):
    MAGIC = 0x0046454B  # "KEF\\0"
    VERSION = 1
    ARCH_I386 = 1
    
    if not os.path.exists(input_bin):
        print(f"[-] Hata: Input binary dosyası bulunamadı: {input_bin}")
        sys.exit(1)
        
    if not os.path.exists(input_elf):
        print(f"[-] Hata: Input ELF dosyası bulunamadı: {input_elf}")
        sys.exit(1)

    with open(input_bin, "rb") as f:
        payload = f.read()
        
    payload_size = len(payload)
    
    HEADER_FORMAT = "<IHHIIII"
    header_size = struct.calcsize(HEADER_FORMAT)
    
    entry_address = get_symbol_offset(input_elf, "_start")
    base_load_address = 0x400000
    if entry_address >= base_load_address:
        entry_offset = entry_address - base_load_address
    else:
        entry_offset = entry_address

    print(f"[+] İşlenen Binary: {input_bin}")
    print(f"[+] Tespit edilen _start adresi: 0x{entry_address:X}")
    print(f"[+] Hesaplanan entry offset: 0x{entry_offset:X}")
    print(f"[+] Gerçek Payload Boyutu: {payload_size} bytes")
    print(f"[+] Header Boyutu: {header_size} bytes")
    print(f"[+] Toplam KEF Boyutu (Header + Payload): {header_size + payload_size} bytes")
    
    flags = 0
    
    header = struct.pack(
        HEADER_FORMAT,
        MAGIC,
        VERSION,
        ARCH_I386,
        entry_offset,
        payload_size,
        flags,
        header_size
    )
    
    with open(output_kef, "wb") as f:
        f.write(header)
        f.write(payload)
        
    print(f"[+] Başarıyla paketlendi: {output_kef}\\n")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Kullanım: python3 kef_format.py <input.bin> <output.kef> <input.elf>")
        sys.exit(1)
        
    format_kef(sys.argv[1], sys.argv[2], sys.argv[3])
"""

def ensure_kry_sdk_on_build():
    """Derleme aşamasında ~/.kry/ ortamının ve gerekli dosyaların eksiksiz olduğunu doğrular, yoksa oluşturur."""
    kry_home = os.path.expanduser("~/.kry")
    kry_include = os.path.join(kry_home, "include")
    api_header_path = os.path.join(kry_include, "kef_api.h")
    linker_path = os.path.join(kry_home, "linker.ld")
    kef_format_py_path = os.path.join(kry_home, "kef_format.py")
    
    os.makedirs(kry_include, exist_ok=True)
    
    # Eğer başlık dosyası yoksa veya içinde vfs_file_info_t eksikse güncel şablonu yaz
    need_write = True
    if os.path.exists(api_header_path):
        with open(api_header_path, "r", encoding="utf-8") as f:
            content = f.read()
            if "vfs_file_info_t" in content:
                need_write = False

    if need_write:
        print(f"[*] Uyarı: '{api_header_path}' eksik veya güncel değil. Yeniden oluşturuluyor...")
        with open(api_header_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_KEF_API_H)
        print(f"[✔] SDK başlık dosyası güncellendi.")
        
    if not os.path.exists(linker_path):
        print(f"[*] Uyarı: '{linker_path}' bulunamadı. Oluşturuluyor...")
        with open(linker_path, "w", encoding="utf-8") as f:
            f.write(LINKER_LD_TEMPLATE)
        print(f"[✔] Merkezi linker betiği oluşturuldu.")
        
    if not os.path.exists(kef_format_py_path):
        print(f"[*] Uyarı: '{kef_format_py_path}' bulunamadı. Oluşturuluyor...")
        with open(kef_format_py_path, "w", encoding="utf-8") as f:
            f.write(KEF_FORMAT_PY_TEMPLATE)
        print(f"[✔] Paketleme betiği oluşturuldu.")

def build_app(args):
    print("[*] KryonOS C uygulaması derleniyor...")
    
    target_dir = args.dir if hasattr(args, 'dir') and args.dir else "."
    if not os.path.exists(target_dir):
        print(f"[-] Hata: Hedef dizin bulunamadı: {target_dir}")
        sys.exit(1)

    ensure_kry_sdk_on_build()

    kry_json_path = os.path.join(target_dir, "kry.json")
    if not os.path.exists(kry_json_path):
        print(f"[-] Hata: '{target_dir}' içinde 'kry.json' konfigürasyon dosyası bulunamadı!")
        sys.exit(1)

    with open(kry_json_path, "r", encoding="utf-8") as f:
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

    global_linker_path = os.path.expanduser("~/.kry/linker.ld")

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
    clean_build = getattr(args, 'clean', False)
    if clean_build and os.path.exists(build_dir):
        print(f"[*] Temizleniyor (-c): {build_dir} siliniyor...")
        shutil.rmtree(build_dir)

    os.makedirs(build_dir, exist_ok=True)

    main_o = os.path.join(build_dir, "main.o")
    target_elf = os.path.join(build_dir, f"{app_name}.elf")
    target_bin = os.path.join(build_dir, f"{app_name}.bin")
    target_kef = os.path.join(target_dir, f"{app_name}.kef")

    format_script = os.path.expanduser("~/.kry/kef_format.py")

    try:
        print(f"[*] Çalıştırılıyor: {compiler} (C Derleme)")
        compile_cmd = [compiler] + c_flags + ["-c", source_path, "-o", main_o]
        subprocess.run(compile_cmd, check=True)

        print(f"[*] Çalıştırılıyor: ld (ELF Linkleme - Linker: {global_linker_path})")
        link_elf_cmd = ["ld"] + pure_linker_flags + [main_o, "-o", target_elf]
        subprocess.run(link_elf_cmd, cwd=target_dir, check=True)

        print("[*] Çalıştırılıyor: objcopy (Binary Çıkartma)")
        subprocess.run(["objcopy", "-O", "binary", target_elf, target_bin], check=True)

        print("[*] Çalıştırılıyor: kef_format paketleme")
        if os.path.exists(format_script):
            pack_cmd = ["python3", format_script, target_bin, target_kef, target_elf]
            subprocess.run(pack_cmd, check=True)
        else:
            print(f"[-] Hata: '{format_script}' bulunamadı!")
            sys.exit(1)

        print(f"[+] Başarılı! Derlenen KEF: {target_kef}")

    except subprocess.CalledProcessError as e:
        print(f"[-] Derleme sırasında hata oluştu (Exit Code: {e.returncode}): {e}")
        sys.exit(1)