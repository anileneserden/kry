import os
import subprocess
import sys
import shutil
import json

# LEXv2 SDK ve format betiği şablonları (Eğer silindiyse otomatik yeniden oluşturmak için)
DEFAULT_LEX2_API_H = """#ifndef LEX2_API_H
#define LEX2_API_H

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

#define LEX_API_TABLE ((struct lex_api_table_t*)0x501000)

struct lex_api_table_t {
    int (*window_create)(const char* title, int width, int height);
    void (*print)(const char* str);
    void (*exit)(void);
    int (*label_create)(int x, int y, uint32_t color, const char* text, uint8_t anchor);
    int (*panel_create)(int x, int y, int w, int h, uint32_t color, uint32_t hover_color, void (*on_click)(void), void (*on_hover)(void), uint8_t anchor);
    int (*button_create)(int x, int y, int w, int h, uint32_t bg_color, uint32_t text_color, const char* text, void (*on_click)(void), uint8_t anchor);
    int (*picturebox_create)(int x, int y, int w, int h, const char* img_path, uint8_t anchor);
    int (*input_create)(int x, int y, int w, int h, 
                        const char* text, const char* placeholdertext, 
                        uint32_t backcolor, uint32_t color, 
                        uint32_t placeholder_color, uint32_t border_color, 
                        int border_thickness, uint8_t anchor);
    int (*input_get_text)(int input_id, char* out_buf, int max_len);
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
static inline int lex_window_create(const char* t, int w, int h) { return LEX_API_TABLE->window_create(t, w, h); }
static inline void lex_print(const char* s) { LEX_API_TABLE->print(s); }
static inline void lex_exit(void) { LEX_API_TABLE->exit(); }

static inline int label(int x, int y, uint32_t c, const char* t, uint8_t a) { return LEX_API_TABLE->label_create(x, y, c, t, a); }
static inline int panel(int x, int y, int w, int h, uint32_t c, uint8_t a) { return LEX_API_TABLE->panel_create(x, y, w, h, c, c, 0, 0, a); }
static inline int lex_panel_create(int x, int y, int w, int h, uint32_t c, uint32_t hc, void (*click)(void), void (*hover)(void), uint8_t a) { 
    return LEX_API_TABLE->panel_create(x, y, w, h, c, hc, click, hover, a); 
}
static inline int button(int x, int y, int w, int h, uint32_t bg, uint32_t fg, const char* t, void (*click)(void), uint8_t a) { 
    return LEX_API_TABLE->button_create(x, y, w, h, bg, fg, t, click, a); 
}

static inline int picturebox(int x, int y, int w, int h, const char* img_path, uint8_t anchor) {
    return LEX_API_TABLE->picturebox_create(x, y, w, h, img_path, anchor);
}

static inline int lex_combobox_create(int x, int y, int w, int h, const char** items, int count, int def_idx, uint32_t bg, uint32_t fg, uint32_t border, uint8_t a) {
    return LEX_API_TABLE->combobox_create(x, y, w, h, items, count, def_idx, bg, fg, border, a);
}

static inline int lex_get_directory_files(const char* path, vfs_file_info_t* list, int max) { 
    return LEX_API_TABLE->get_directory_files(path, list, max); 
}
static inline void* lex_read_file(const char* path, uint32_t* size) { 
    return LEX_API_TABLE->read_file(path, size); 
}

static inline size_t lex_strlen(const char* str) { return LEX_API_TABLE->strlen(str); }
static inline int lex_strcmp(const char* s1, const char* s2) { return LEX_API_TABLE->strcmp(s1, s2); }

static inline void backgroundColor(uint32_t color) { LEX_API_TABLE->background_color(color); }
static inline void background_color(uint32_t color) { LEX_API_TABLE->background_color(color); }

static inline bool is_key_pressed(int key_code) { return LEX_API_TABLE->is_key_pressed(key_code); }

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

LEX2_FORMAT_PY_TEMPLATE = """#!/usr/bin/env python3
import sys
import struct
import os

def format_lex2(input_bin, output_lex, input_elf):
    MAGIC = 0x0058454C
    VERSION = 1
    ARCHITECTURE_I386 = 1
    FLAGS = 0
    
    if not os.path.exists(input_bin):
        print(f"[-] Hata: Input binary dosyasi bulunamadi: {input_bin}")
        sys.exit(1)
        
    if not os.path.exists(input_elf):
        print(f"[-] Hata: Input ELF dosyasi bulunamadi: {input_elf}")
        sys.exit(1)

    with open(input_bin, "rb") as f:
        payload = f.read()
        
    payload_size = len(payload)
    
    output_dir = os.path.dirname(os.path.abspath(output_lex))
    resources_dir_path = os.path.join(output_dir, "resources")
    
    resource_entries = []
    resources_payload = bytearray()
    
    if os.path.exists(resources_dir_path) and os.path.isdir(resources_dir_path):
        print(f"[*] Kaynak dizini taranior: {resources_dir_path}")
        for filename in os.listdir(resources_dir_path):
            file_full_path = os.path.join(resources_dir_path, filename)
            if os.path.isfile(file_full_path):
                with open(file_full_path, "rb") as rf:
                    file_data = rf.read()
                
                stored_name = f"resources/{filename}"
                
                resource_entries.append({
                    "name": stored_name,
                    "data": file_data,
                    "size": len(file_data)
                })
                print(f"  [+] Kaynak bulundu ve yuklendi: {stored_name} ({len(file_data)} bytes)")
    else:
        print(f"[*] Bilgi: '{resources_dir_path}' klasoru bulunamadi, kaynak eklenmeyecek.")

    section_count = 2 if resource_entries else 1
    
    HEADER_FORMAT = "<IHHII"
    header_size = struct.calcsize(HEADER_FORMAT)
    
    SECTION_HEADER_FORMAT = "<III"
    section_header_size = struct.calcsize(SECTION_HEADER_FORMAT)
    
    text_section_offset = header_size + (section_count * section_header_size)
    text_section_size = payload_size
    
    current_offset = text_section_offset + text_section_size
    
    if resource_entries:
        for res in resource_entries:
            name_bytes = res["name"].encode('utf-8') + b'\\x00' if False else res["name"].encode('utf-8') + b'\\x00'.replace(b'\\\\x00', b'\\x00') # guvenli null byte
            # Alternatif temiz null ekleme: res["name"].encode('utf-8') + b'\\x00' yerine dogrudan b'\\0'
            name_bytes = res["name"].encode('utf-8') + b'\\x00'.replace(b'\\\\x00', b'\\x00')
            
            # Daha sade ve temiz hali:
            name_bytes = res["name"].encode('utf-8') + b'\\0' # Python bunu dogru yorumlar
            
    if resource_entries:
        for res in resource_entries:
            resources_payload.extend(res["name"].encode('utf-8') + b'\\x00')
            resources_payload.extend(struct.pack("<I", res["size"]))
            resources_payload.extend(res["data"])
            resources_payload.extend(b"IMGEND")
    
    header = struct.pack(HEADER_FORMAT, MAGIC, VERSION, ARCHITECTURE_I386, section_count, FLAGS)
    
    LEX2_SECTION_TEXT = 1
    LEX2_SECTION_RESOURCES = 2
    
    print(f"[+] Islenen Binary: {input_bin}")
    print(f"[+] LEXv2 Paketleme: Section Count = {section_count}, Kaynak Sayisi = {len(resource_entries)}")
    
    with open(output_lex, "wb") as f:
        f.write(header)
        f.write(struct.pack(SECTION_HEADER_FORMAT, LEX2_SECTION_TEXT, text_section_offset, text_section_size))
        
        if resource_entries:
            res_section_offset = current_offset
            res_section_size = len(resources_payload)
            f.write(struct.pack(SECTION_HEADER_FORMAT, LEX2_SECTION_RESOURCES, res_section_offset, res_section_size))
            
        f.write(payload)
        if resource_entries:
            f.write(resources_payload)
            
    print(f"[+] Basariyla LEXv2 formatinda paketlendi: {output_lex}\\n")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Kullanim: python3 lex2_format.py <input.bin> <output.lex> <input.elf>")
        sys.exit(1)
        
    format_lex2(sys.argv[1], sys.argv[2], sys.argv[3])
"""

def ensure_lnr_sdk_on_build():
    """Derleme aşamasında ~/.lnr/ ortamının ve gerekli LEXv2 dosyalarının eksiksiz ve güncel olduğunu doğrular."""
    lnr_home = os.path.expanduser("~/.lnr")
    lnr_include = os.path.join(lnr_home, "include")
    api_header_path = os.path.join(lnr_include, "lex2_api.h")
    linker_path = os.path.join(lnr_home, "linker.ld")
    lex_format_py_path = os.path.join(lnr_home, "lex2_format.py")
    
    os.makedirs(lnr_include, exist_ok=True)
    
    # 1. lex2_api.h kontrolü ve otomatik güncelleme
    need_write_api = True
    if os.path.exists(api_header_path):
        with open(api_header_path, "r", encoding="utf-8") as f:
            content = f.read()
            # Eğer şablondaki tüm anahtar kelimeler ve yeni picturebox_create mevcutsa tekrar yazma
            if "vfs_file_info_t" in content and "LEX2_API_H" in content and "picturebox_create" in content:
                need_write_api = False

    if need_write_api:
        print(f"[*] Bilgi: '{api_header_path}' eksik veya güncel değil. Otomatik güncelleniyor...")
        with open(api_header_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_LEX2_API_H)
        print(f"[✔] LEXv2 SDK başlık dosyası güncellendi.")
        
    # 2. linker.ld kontrolü
    if not os.path.exists(linker_path):
        print(f"[*] Bilgi: '{linker_path}' bulunamadı. Oluşturuluyor...")
        with open(linker_path, "w", encoding="utf-8") as f:
            f.write(LINKER_LD_TEMPLATE)
        print(f"[✔] Merkezi linker betiği oluşturuldu.")
        
    # 3. lex2_format.py kontrolü
    if not os.path.exists(lex_format_py_path):
        print(f"[*] Bilgi: '{lex_format_py_path}' bulunamadı. Oluşturuluyor...")
        with open(lex_format_py_path, "w", encoding="utf-8") as f:
            f.write(LEX2_FORMAT_PY_TEMPLATE)
        print(f"[✔] LEXv2 paketleme betiği oluşturuldu.")

def build_app(args):
    print("[*] LenorOS C uygulaması LEXv2 formatında derleniyor...")
    
    target_dir = args.dir if hasattr(args, 'dir') and args.dir else "."
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
    clean_build = getattr(args, 'clean', False)
    if clean_build and os.path.exists(build_dir):
        print(f"[*] Temizleniyor (-c): {build_dir} siliniyor...")
        shutil.rmtree(build_dir)

    os.makedirs(build_dir, exist_ok=True)

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