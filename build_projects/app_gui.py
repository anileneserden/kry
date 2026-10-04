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

static inline int kef_window_create(const char* t, int w, int h) { return KEF_API_TABLE->window_create(t, w, h); }
static inline void kef_print(const char* s) { KEF_API_TABLE->print(s); }
static inline int label(int x, int y, uint32_t c, const char* t, uint8_t a) { return KEF_API_TABLE->label_create(x, y, c, t, a); }
static inline int panel(int x, int y, int w, int h, uint32_t c, uint8_t a) { return KEF_API_TABLE->panel_create(x, y, w, h, c, c, 0, 0, a); }

#endif
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
    header_size = 28  
    
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
    print(f"[+] Toplam KEF Boyutu (Header + Payload): {header_size + payload_size} bytes")
    
    flags = 0
    
    header = struct.pack(
        "<IHHIIII",
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
    kef_format_py_path = os.path.join(kry_home, "kef_format.py")
    
    os.makedirs(kry_include, exist_ok=True)
    
    if not os.path.exists(api_header_path):
        print(f"[*] Uyarı: '{api_header_path}' bulunamadı. Derleme için otomatik olarak yeniden oluşturuluyor...")
        with open(api_header_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_KEF_API_H)
        print(f"[✔] SDK başlık dosyası oluşturuldu.")
        
    if not os.path.exists(kef_format_py_path):
        print(f"[*] Uyarı: '{kef_format_py_path}' bulunamadı. Paketleme için otomatik olarak yeniden oluşturuluyor...")
        with open(kef_format_py_path, "w", encoding="utf-8") as f:
            f.write(KEF_FORMAT_PY_TEMPLATE)
        print(f"[✔] Paketleme betiği oluşturuldu.")

def build_app(args):
    print("[*] KryonOS C uygulaması derleniyor...")
    
    target_dir = args.dir if hasattr(args, 'dir') and args.dir else "."
    if not os.path.exists(target_dir):
        print(f"[-] Hata: Hedef dizin bulunamadı: {target_dir}")
        sys.exit(1)

    # DERLEME ÖNCESİ GÜVENCE: SDK veya format scripti silindiyse build aşamasında otomatik tamamla
    ensure_kry_sdk_on_build()

    kry_json_path = os.path.join(target_dir, "kry.json")
    if not os.path.exists(kry_json_path):
        print(f"[-] Hata: '{target_dir}' içinde 'kry.json' konfigürasyon dosyası bulunamadı!")
        sys.exit(1)

    # kry.json oku
    with open(kry_json_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    app_name = config.get("name", "app")
    source_file = config.get("source", "main.c")
    compiler = config.get("compiler", "gcc")
    raw_c_flags = config.get("c-flags", [])
    linker_flags = config.get("linker-flags", [])

    # Tilde (~) işaretini tam ev dizini yoluna genişlet
    c_flags = []
    for flag in raw_c_flags:
        if flag.startswith("-I"):
            path_part = flag[2:]
            expanded_path = os.path.expanduser(path_part)
            c_flags.append(f"-I{expanded_path}")
        else:
            c_flags.append(os.path.expanduser(flag))

    # Eğer linker bayraklarında --oformat binary varsa geçici olarak kaldırıyoruz (ELF lazım)
    pure_linker_flags = []
    skip_next = False
    for flag in linker_flags:
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

    # Dosya yolları
    main_o = os.path.join(build_dir, "main.o")
    target_elf = os.path.join(build_dir, f"{app_name}.elf")
    target_bin = os.path.join(build_dir, f"{app_name}.bin")
    target_kef = os.path.join(target_dir, f"{app_name}.kef")

    format_script = os.path.expanduser("~/.kry/kef_format.py")

    try:
        # 1. Adım: Saf C Derleme (gcc)
        print(f"[*] Çalıştırılıyor: {compiler} (C Derleme)")
        compile_cmd = [compiler] + c_flags + ["-c", source_path, "-o", main_o]
        subprocess.run(compile_cmd, check=True)

        # 2. Adım: ELF Bağlama (ld)
        print("[*] Çalıştırılıyor: ld (ELF Linkleme)")
        link_elf_cmd = ["ld"] + pure_linker_flags + [main_o, "-o", target_elf]
        subprocess.run(link_elf_cmd, cwd=target_dir, check=True)

        # 3. Adım: ELF'ten Ham Binary Çıkartma (objcopy)
        print("[*] Çalıştırılıyor: objcopy (Binary Çıkartma)")
        subprocess.run(["objcopy", "-O", "binary", target_elf, target_bin], check=True)

        # 4. Adım: KEF Paketleme
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