#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess

# Şablon Kodlar (Python format karışıklığı olmaması için { -> {{ ve } -> }} yapıldı, sadece {app_name} değişecek)
MAIN_C_TEMPLATE = """#include <kef.h>

void main(void) {
    // Pencere oluştur (Genişlik, Yükseklik, Başlık)
    int win = kef_window_create("{app_name}", 400, 300);
    if (!win) return;

    kef_serial_write("[{app_name}] Uygulama baslatildi!\\n");

    // Arayüz bileşenleri
    kef_draw_text(16, 40, "Merhaba KuvixOS!", 0xFFFFFFFF);
    kef_draw_rect(16, 70, 120, 40, 0xFF00FF00);
    kef_draw_button(16, 130, 100, 30, "Tikla", 0xFF007ACC);

    while (1) {
        // Uygulama ana döngüsü
    }
}
"""

MAKEFILE_TEMPLATE = """TARGET = {app_slug}
CC = gcc
LD = ld

CFLAGS = -m32 -ffreestanding -fno-pie -fno-stack-protector -fno-builtin -I../../include -O2
LDFLAGS = -m elf_i386 -T linker.ld --oformat binary

all: $(TARGET).kef

$(TARGET).kef: $(TARGET).bin
\tpython3 ../../kef_format.py $(TARGET).bin $(TARGET).kef "{author}" "{version}"

$(TARGET).bin: $(TARGET).elf
\t$(LD) $(LDFLAGS) -o $(TARGET).bin $(TARGET).elf

$(TARGET).elf: main.o
\t$(LD) -m elf_i386 -T linker.ld -o $(TARGET).elf main.o

main.o: main.c
\t$(CC) $(CFLAGS) -c main.c -o main.o

clean:
\trm -rf build *.o *.elf *.bin *.kef
"""

LINKER_LD_TEMPLATE = """ENTRY(main)
SECTIONS
{
    . = 0x00000000;
    .text : { *(.text) }
    .data : { *(.data) }
    .bss : { *(.bss COMMON) }
}
"""

def cmd_init(args):
    target_dir = args.dir if args.dir else "."
    app_name = args.name
    app_slug = app_name.lower().replace(" ", "_")
    
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
        print(f"[+] Dizin olusturuldu: {target_dir}")

    main_c_path = os.path.join(target_dir, "main.c")
    makefile_path = os.path.join(target_dir, "Makefile")
    linker_path = os.path.join(target_dir, "linker.ld")

    main_c_content = MAIN_C_TEMPLATE.replace("{app_name}", app_name)
    with open(main_c_path, "w", encoding="utf-8") as f:
        f.write(main_c_content)
    print(f"[+] {main_c_path} olusturuldu.")

    makefile_content = (MAKEFILE_TEMPLATE
                        .replace("{app_slug}", app_slug)
                        .replace("{author}", args.author)
                        .replace("{version}", args.version))
    with open(makefile_path, "w", encoding="utf-8") as f:
        f.write(makefile_content)
    print(f"[+] {makefile_path} olusturuldu.")

    with open(linker_path, "w", encoding="utf-8") as f:
        f.write(LINKER_LD_TEMPLATE)
    print(f"[+] {linker_path} olusturuldu.")

    print(f"\nBasariyla '{app_name}' uygulamasi {target_dir} icinde hazirlandi!")

def cmd_fs_mount(args):
    image_path = args.image
    mount_point = args.mountpoint

    print(f"[*] Dosya sistemi bağlanıyor...")
    print(f"    İmaj: {image_path}")
    print(f"    Hedef Dizin: {mount_point}")
    
    if not os.path.exists(image_path):
        print(f"[-] Hata: İmaj dosyası bulunamadı: {image_path}")
        sys.exit(1)
        
    if not os.path.exists(mount_point):
        os.makedirs(mount_point, exist_ok=True)

    # Buraya ileride KryFSMountSystem (FUSE) entegrasyonunu bağlayacağız
    print("[+] Mount altyapısı hazır. FUSE entegrasyonu yazılmayı bekliyor.")

def main():
    parser = argparse.ArgumentParser(description="KuvixOS SDK CLI (kry)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init komutu
    parser_init = subparsers.add_parser("init", help="Yeni bir uygulama iskeleti olusturur.")
    parser_init.add_argument("-t", "--type", required=True, choices=["gui", "cli"], help="Uygulama tipi")
    parser_init.add_argument("-n", "--name", required=True, help="Uygulama adi")
    parser_init.add_argument("-d", "--dir", help="Hedef dizin")
    parser_init.add_argument("-a", "--author", default="Kuvix Developer", help="Yazar adi")
    parser_init.add_argument("-v", "--version", default="1.0.0", help="Uygulama surumu")
    parser_init.set_defaults(func=cmd_init)

    # fs alt komutları (kry fs mount ...)
    parser_fs = subparsers.add_parser("fs", help="KRYFS dosya sistemi işlemleri")
    fs_subparsers = parser_fs.add_subparsers(dest="fs_command", required=True)

    parser_mount = fs_subparsers.add_parser("mount", help="KRYFS imajını FUSE ile bağlar")
    parser_mount.add_argument("image", help="KRYFS imaj dosyasının yolu (.img)")
    parser_mount.add_argument("mountpoint", help="Bağlanacak hedef klasör")
    parser_mount.set_defaults(func=cmd_fs_mount)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()