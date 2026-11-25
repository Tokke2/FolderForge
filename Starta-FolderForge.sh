#!/bin/sh
# User entry point for Linux; also used by the bundled macOS .app.
# No remote shell scripts, package maintenance, pip or Python upgrades.
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
OS=$(uname -s)

notify() {
    if [ "$OS" = Darwin ]; then
        /usr/bin/osascript - "$1" <<'APPLESCRIPT' >/dev/null 2>&1
on run argv
    display dialog (item 1 of argv) with title "FolderForge" buttons {"OK"} default button "OK"
end run
APPLESCRIPT
    elif command -v zenity >/dev/null 2>&1; then
        zenity --info --title=FolderForge --text="$1" >/dev/null 2>&1
    elif command -v kdialog >/dev/null 2>&1; then
        kdialog --msgbox "$1" --title FolderForge >/dev/null 2>&1
    fi
}
confirm_missing() {
    message='Ingen Python-installation hittades. Vill du installera Python? Befintlig Homebrew på macOS eller systemets paketkälla på Linux används. Det kan vara äldre än senaste python.org-versionen och kan kräva IT-behörighet. Finns ingen lämplig installationsväg erbjuds den officiella nedladdningssidan. Inga Python- eller apppaket uppgraderas rutinmässigt; extra paket i requirements.txt installeras inte.'
    if [ "$OS" = Darwin ]; then
        answer=$(/usr/bin/osascript - "$message" <<'APPLESCRIPT' 2>/dev/null
on run argv
    display dialog (item 1 of argv) with title "FolderForge - Python saknas" buttons {"Avbryt", "Installera"} default button "Avbryt" cancel button "Avbryt"
    return button returned of result
end run
APPLESCRIPT
)
        [ "$answer" = Installera ]
    elif command -v zenity >/dev/null 2>&1; then
        zenity --question --default-cancel --title='FolderForge - Python saknas' --text="$message" >/dev/null 2>&1
    elif command -v kdialog >/dev/null 2>&1; then
        kdialog --warningyesno "$message" --defaultno --title FolderForge >/dev/null 2>&1
    else
        # No terminal fallback: without a native consent dialog, do nothing.
        return 1
    fi
}
consider_python() {
    candidate=$1
    [ -x "$candidate" ] || return 0
    # Apple's developer-tools stub can offer a large unrelated tools install.
    if [ "$OS" = Darwin ] && [ "$candidate" = /usr/bin/python3 ]; then
        /usr/bin/xcode-select -p >/dev/null 2>&1 || return 0
    fi
    PYTHON_PRESENT=1
    [ -z "$PYTHON_COMMAND" ] || return 0
    identity=$("$candidate" --version 2>&1) || return 0
    case "$identity" in
        Python\ [0-9]*) PYTHON_COMMAND=$candidate ;;
    esac
}
find_python() {
    PYTHON_PRESENT=0
    PYTHON_COMMAND=
    for name in python3 python; do
        location=$(command -v "$name" 2>/dev/null) || location=
        [ -z "$location" ] || consider_python "$location"
    done
    for location in /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3 \
        /usr/bin/python /Library/Frameworks/Python.framework/Versions/*/bin/python3; do
        consider_python "$location"
    done
}
install_missing() {
    # Caller has obtained consent. Recheck so an existing interpreter is NEVER upgraded.
    find_python
    [ "$PYTHON_PRESENT" -eq 0 ] || return 0
    if [ "$OS" = Darwin ]; then
        brew_path=$(command -v brew 2>/dev/null) || brew_path=
        for path in "$brew_path" /opt/homebrew/bin/brew /usr/local/bin/brew; do
            if [ -n "$path" ] && [ -x "$path" ]; then
                HOMEBREW_NO_AUTO_UPDATE=1 "$path" install python
                return $?
            fi
        done
        /usr/bin/open 'https://www.python.org/downloads/macos/'
        notify 'Den officiella sidan är öppnad. Installera en stabil Python enligt IT-policy och starta FolderForge igen. Ingen Homebrew eller utvecklarverktyg installeras av appen.'
        return 1
    fi
    if ! command -v pkexec >/dev/null 2>&1; then
        notify 'Grafisk behörighetsbekräftelse (pkexec) saknas. Be IT installera Python 3.11+ med Tkinter. Ingen installation har körts.'
        return 1
    fi
    if command -v apt-get >/dev/null 2>&1; then
        pkexec "$(command -v apt-get)" install -y python3 python3-tk
    elif command -v dnf >/dev/null 2>&1; then
        pkexec "$(command -v dnf)" install -y python3 python3-tkinter
    elif command -v zypper >/dev/null 2>&1; then
        pkexec "$(command -v zypper)" --non-interactive install python3 python3-tk
    elif command -v pacman >/dev/null 2>&1; then
        pkexec "$(command -v pacman)" -S --needed --noconfirm python tk
    else
        notify 'Ingen stödd paketkälla hittades. Be IT installera Python 3.11+ med Tkinter. Ingen installation har körts.'
        return 1
    fi
}
start_or_offer() {
    find_python
    if [ "$PYTHON_PRESENT" -eq 0 ]; then
        lock="$ROOT/logs/python-first-install.lock"
        if ! mkdir "$lock" 2>/dev/null; then
            notify 'En Python-installation kan redan pågå. Kontrollera logs/python-first-install.lock om en tidigare start avbröts.'
            return 1
        fi
        trap 'rmdir "$lock" 2>/dev/null || :' EXIT
        trap 'rmdir "$lock" 2>/dev/null || :; exit 1' HUP INT TERM
        find_python
        result=0
        if [ "$PYTHON_PRESENT" -eq 0 ]; then
            if confirm_missing; then install_missing; result=$?; else result=125; fi
        fi
        rmdir "$lock" 2>/dev/null || :
        trap - EXIT HUP INT TERM
        [ "$result" -ne 125 ] || return 0
        [ "$result" -eq 0 ] || return "$result"
        find_python
    fi
    if [ -z "$PYTHON_COMMAND" ]; then
        notify 'Python finns men kunde inte köras. Ingen installation eller uppgradering erbjuds. Se logs/start-python.log och kontakta IT.'
        return 1
    fi
    if ! "$PYTHON_COMMAND" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
        notify 'Python finns men FolderForge kräver Python 3.11+. Ingen installation eller uppgradering erbjuds automatiskt.'
        return 1
    fi
    "$PYTHON_COMMAND" "$ROOT/Starta-FolderForge.py"
}
# MAIN -- tests source only the functions above, never a real installer.
case "$OS" in Darwin|Linux) ;; *) exit 1 ;; esac
mkdir -p "$ROOT/logs" || exit 1
exec >>"$ROOT/logs/start-python.log" 2>&1
start_or_offer
