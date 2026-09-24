#!/usr/bin/env python3
import sys
import argparse
import os
import json
import termios
import tty

from create_projects import app_gui as create_gui
from build_projects import app_gui as build_gui

PROJECT_CREATORS = {
    "app-gui": create_gui.create_app
}

PROJECT_BUILDERS = {
    "app-gui": build_gui.build_app
}

CONFIG_FILE = os.path.expanduser("~/.kry/config.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"editor": "vscode"}

def save_config(config):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

def get_key():
    """Terminalden ham tuş girdisini (ok tuşları ve enter) okur."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == '\x1b':
            ch2 = sys.stdin.read(1)
            if ch2 == '[':
                ch3 = sys.stdin.read(1)
                if ch3 == 'C': return 'RIGHT'
                if ch3 == 'D': return 'LEFT'
        elif ch == '\r' or ch == '\n':
            return 'ENTER'
        elif ch == '\x03': # Ctrl+C
            raise KeyboardInterrupt
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return None

def arrow_select(options, title="Seçim yapın"):
    """Sağ/Sol ok tuşlarıyla yatay eksende renkli seçim yapmayı sağlar."""
    current = 0
    sys.stdout.write("\x1b[?25l") # İmleci gizle
    try:
        while True:
            # Satırı temizle ve güncel seçenekleri yazdır
            output = f"\r\033[K\033[1;36m{title}:\033[0m"
            for i, opt in enumerate(options):
                if i == current:
                    # Seçili olan: Parlak Yeşil ve Köşeli Parantez
                    output += f"   \033[1;32m[ {opt} ]\033[0m"
                else:
                    # Seçili olmayan: Sönük/Gri
                    output += f"   \033[2m  {opt}  \033[0m"
            
            sys.stdout.write(output)
            sys.stdout.flush()

            key = get_key()
            if key == 'LEFT':
                current = (current - 1) % len(options)
            elif key == 'RIGHT':
                current = (current + 1) % len(options)
            elif key == 'ENTER':
                print() # Alt satıra geç
                break
    finally:
        sys.stdout.write("\x1b[?25h") # İmleci tekrar göster
        sys.stdout.flush()
    return options[current]

def cmd_settings(args):
    config = load_config()
    current_editor = config.get("editor", "vscode")

    print("\033[1;33m--- KuvixOS SDK (kry) Ayarları ---\033[0m")
    available_editors = ["vscode", "cursor", "sublime", "nano", "yok"]
    
    print(f"Mevcut Varsayılan Editör: \033[1m{current_editor}\033[0m")
    print("Yeni bir editör seçmek için sağ/sol ok tuşlarını kullanın:")
    
    selected_editor = arrow_select(available_editors, title="Kod Editörü")
    
    if selected_editor:
        config["editor"] = selected_editor
        save_config(config)
        print(f"\033[1;32m[+] Başarılı!\033[0m Varsayılan kod editörü '\033[1m{selected_editor}\033[0m' olarak güncellendi.")

def cmd_init(args):
    config = load_config()
    default_editor = config.get("editor", "vscode")

    app_type = args.type
    if not app_type:
        # İnteraktif Sağ/Sol Ok Tuşlu Seçim Ekranı
        app_type = arrow_select(list(PROJECT_CREATORS.keys()), title="Uygulama Tipi Seçin")

    if app_type not in PROJECT_CREATORS:
        print(f"[-] Hata: Geçersiz uygulama tipi '{app_type}'.")
        sys.exit(1)

    app_name = args.name
    if not app_name:
        app_name = input("\033[1;36mUygulama adı (örn: TestApp):\033[0m ").strip()
        if not app_name:
            print("[-] Hata: Uygulama adı boş olamaz!")
            sys.exit(1)

    target_dir = args.dir
    if not target_dir:
        default_dir = app_name.lower().replace(" ", "_")
        target_dir = input(f"\033[1;36mHedef dizin [{default_dir}]:\033[0m ").strip() or default_dir

    author = args.author
    if author == "Kuvix Developer":
        user_author = input(f"\033[1;36mYazar adı [{author}]:\033[0m ").strip()
        if user_author:
            author = user_author

    version = args.version
    if version == "1.0.0":
        user_version = input(f"\033[1;36mSürüm [{version}]:\033[0m ").strip()
        if user_version:
            version = user_version

    editor = args.editor if args.editor else default_editor

    args.type = app_type
    args.name = app_name
    args.dir = target_dir
    args.author = author
    args.version = version
    args.editor = editor

    PROJECT_CREATORS[app_type](args)

def cmd_build(args):
    app_type = getattr(args, 'type', 'app-gui')
    if app_type not in PROJECT_BUILDERS:
        print(f"[-] Hata: Geçersiz veya desteklenmeyen derleme tipi '{app_type}'.")
        sys.exit(1)
    PROJECT_BUILDERS[app_type](args)

def main():
    parser = argparse.ArgumentParser(description="KuvixOS SDK CLI (kry)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_init = subparsers.add_parser("init", help="Yeni bir uygulama iskeleti oluşturur.")
    parser_init.add_argument("-t", "--type", choices=list(PROJECT_CREATORS.keys()), help="Uygulama tipi")
    parser_init.add_argument("-n", "--name", help="Uygulama adı")
    parser_init.add_argument("-d", "--dir", help="Hedef dizin")
    parser_init.add_argument("-a", "--author", default="Kuvix Developer", help="Yazar adı")
    parser_init.add_argument("-v", "--version", default="1.0.0", help="Uygulama sürümü")
    parser_init.add_argument("-e", "--editor", help="Editör yapılandırma tipi")
    parser_init.set_defaults(func=cmd_init)

    # build komutu
    parser_build = subparsers.add_parser("build", help="Mevcut uygulama projesini derler ve paketler.")
    parser_build.add_argument("-t", "--type", default="app-gui", choices=list(PROJECT_BUILDERS.keys()), help="Uygulama tipi")
    parser_build.add_argument("-d", "--dir", help="Proje dizini", default=".")
    parser_build.add_argument("-c", "--clean", action="store_true", help="Build klasörünü temizleyip sıfırdan derler")
    parser_build.set_defaults(func=cmd_build)

    parser_settings = subparsers.add_parser("settings", help="KuvixOS SDK global ayarlarını yönetir.")
    parser_settings.set_defaults(func=cmd_settings)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()