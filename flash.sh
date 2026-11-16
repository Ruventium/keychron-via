#!/usr/bin/env bash
# Прошивка Keychron Q14 Pro через STM32 DFU (Linux, без Windows и QMK Toolbox).
#
#   ./flash.sh          — прошить (клавиатура уже в режиме DFU)
#   ./flash.sh --wait   — снять бэкап, затем ждать DFU и прошить
#
# Порядок: бэкап раскладки (пока клавиатура ещё в обычном режиме) -> DFU ->
# прошивка -> ожидание возврата -> восстановление раскладки.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FW="${FW:-/home/ruventium/Downloads/q14_pro_ansi_encoder_v1.02_20230824.bin}"
BACKUP_DIR="$HERE/backups"
DFU_VIDPID="0483:df11"

say() { printf '\033[1;36m%s\033[0m\n' "$*"; }
ok()  { printf '\033[1;32m✔ %s\033[0m\n' "$*"; }
warn(){ printf '\033[1;33m! %s\033[0m\n' "$*"; }
die() { printf '\033[1;31m✘ %s\033[0m\n' "$*" >&2; exit 1; }

command -v dfu-util >/dev/null || die "dfu-util не установлен (emerge app-mobilephone/dfu-util)"
[ -f "$FW" ] || die "файл прошивки не найден: $FW"

dfu_present() { dfu-util -l 2>/dev/null | grep -qi "$DFU_VIDPID"; }
kbd_present() { python3 -I "$HERE/via.py" info >/dev/null 2>&1; }

# --- 1. Бэкап, пока клавиатура в обычном режиме ---
mkdir -p "$BACKUP_DIR"
BK="$BACKUP_DIR/$(date +%Y%m%d-%H%M%S)-preflash.json"

if dfu_present; then
    warn "клавиатура уже в режиме DFU — бэкап снять нельзя"
    BK=""
    if [ -f "$BACKUP_DIR/20261116-061630-preflash.json" ]; then
        BK="$BACKUP_DIR/20261116-061630-preflash.json"
        warn "использую ранее снятый бэкап: $(basename "$BK")"
    fi
elif kbd_present; then
    if python3 -I "$HERE/via.py" dump "$BK"; then
        ok "бэкап раскладки: $BK"
    else
        warn "бэкап не снялся — продолжаю без него"
        BK=""
    fi
else
    warn "клавиатура не отвечает по VIA — бэкап пропущен"
    BK=""
fi

# --- 2. Ждём DFU ---
if [ "${1:-}" = "--wait" ]; then
    echo
    say "Переведи клавиатуру в режим прошивки:"
    echo "  отключи USB → зажми Esc (верхняя левая клавиша) → подключи кабель → отпусти Esc"
    echo
    for i in $(seq 1 120); do
        if dfu_present; then ok "DFU найден через ${i}с"; break; fi
        printf '.'
        sleep 1
        [ "$i" = "120" ] && { echo; die "DFU не появился за 120 секунд"; }
    done
    echo
fi

dfu_present || die "DFU-устройство $DFU_VIDPID не найдено"

echo
dfu-util -l 2>/dev/null | grep -i "$DFU_VIDPID" || true
echo

# --- 3. Прошивка ---
say "Прошиваю: $(basename "$FW") ($(stat -c%s "$FW") байт) → 0x08000000"
if ! dfu-util -d "$DFU_VIDPID" -a 0 -s 0x08000000:leave -D "$FW"; then
    die "dfu-util завершился с ошибкой — клавиатура, скорее всего, всё ещё в DFU, повтори запуск"
fi

ok "прошивка записана"
echo

# --- 4. Ждём возврат ---
say "Жду возврата клавиатуры в обычный режим..."
for i in $(seq 1 40); do
    if kbd_present; then ok "клавиатура на связи (${i}с)"; break; fi
    printf '.'
    sleep 1
done
echo

# --- 5. Восстановление раскладки ---
if [ -n "$BK" ] && [ -f "$BK" ]; then
    say "Восстанавливаю раскладку из $(basename "$BK")"
    python3 -I "$HERE/via.py" restore "$BK" || warn "восстановление не удалось — сделай вручную"
else
    warn "бэкапа нет — раскладку придётся настроить заново"
fi

echo
say "Состояние устройства:"
python3 -I "$HERE/via.py" info 2>/dev/null || warn "устройство не отвечает"
