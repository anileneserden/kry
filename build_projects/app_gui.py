import os
import subprocess
import sys
import shutil
import json

def build_app(args):
    print("[*] KryonOS C uygulaması derleniyor...")
    
    target_dir = args.dir if hasattr(args, 'dir') and args.dir else "."
    if not os.path.exists(target_dir):
        print(f"[-] Hata: Hedef dizin bulunamadı: {target_dir}")
        sys.exit(1)

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

    # Tilde (~) işaretini tam ev dizini yoluna genişlet (Örn: -I~/.kry/include -> -I/home/kullanici/.kry/include)
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

        # 2. Adım: ELF Bağlama (ld) - Sembollerin okunabilmesi için önce ELF üretilir
        print("[*] Çalıştırılıyor: ld (ELF Linkleme)")
        link_elf_cmd = ["ld"] + pure_linker_flags + [main_o, "-o", target_elf]
        subprocess.run(link_elf_cmd, cwd=target_dir, check=True)

        # 3. Adım: ELF'ten Ham Binary Çıkartma (objcopy)
        print("[*] Çalıştırılıyor: objcopy (Binary Çıkartma)")
        subprocess.run(["objcopy", "-O", "binary", target_elf, target_bin], check=True)

        # 4. Adım: KEF Paketleme (kef_format.py ile 32-byte header ve entry_offset ekleme)
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