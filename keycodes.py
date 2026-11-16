"""Таблица QMK/VIA keycode'ов для Keychron Q14 Pro.

Ключевой диапазон VIA:
    0x0000-0x00FF  базовые клавиши
    0x2000-0x2FFF  mod-tap
    0x5000-0x51FF  переключение слоя (TG/DF/OSL/TT)
    0x5200-0x52FF  MO(layer)
    0x5300-0x53FF  TO(layer)
    0x7000-0x70FF  пользовательские (старый VIA)
    0x7800-0x78FF  подсветка
    0x7E00-0x7E3F  кастомные Keychron (QK_KB_n)
"""

# --- базовые клавиши: код -> (короткое имя, категория) ---
BASIC = {}

for i, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    BASIC[0x04 + i] = (ch, "letters")
for i, ch in enumerate("1234567890"):
    BASIC[0x1E + i] = (ch, "letters")

BASIC.update({
    0x0000: ("·", "special"),      # KC_NO
    0x0001: ("▽", "special"),      # KC_TRNS
    0x0028: ("Enter", "control"),
    0x0029: ("Esc", "control"),
    0x002A: ("Bksp", "control"),
    0x002B: ("Tab", "control"),
    0x002C: ("Space", "control"),
    0x002D: ("-", "symbols"),
    0x002E: ("=", "symbols"),
    0x002F: ("[", "symbols"),
    0x0030: ("]", "symbols"),
    0x0031: ("\\", "symbols"),
    0x0032: ("#", "symbols"),
    0x0033: (";", "symbols"),
    0x0034: ("'", "symbols"),
    0x0035: ("`", "symbols"),
    0x0036: (",", "symbols"),
    0x0037: (".", "symbols"),
    0x0038: ("/", "symbols"),
    0x0039: ("Caps", "control"),
    0x0046: ("PrtSc", "control"),
    0x0047: ("ScrLk", "control"),
    0x0048: ("Pause", "control"),
    0x0049: ("Ins", "control"),
    0x004A: ("Home", "control"),
    0x004B: ("PgUp", "control"),
    0x004C: ("Del", "control"),
    0x004D: ("End", "control"),
    0x004E: ("PgDn", "control"),
    0x004F: ("→", "control"),
    0x0050: ("←", "control"),
    0x0051: ("↓", "control"),
    0x0052: ("↑", "control"),
    0x0053: ("NumLk", "control"),
    0x0054: ("KP/", "control"),
    0x0055: ("KP*", "control"),
    0x0056: ("KP-", "control"),
    0x0057: ("KP+", "control"),
    0x0058: ("KPEnt", "control"),
    0x0062: ("KP0", "control"),
    0x0063: ("KP.", "control"),
    0x0064: ("\\|", "symbols"),
    0x0065: ("Menu", "control"),
    0x0067: ("KP=", "control"),
    0x0076: ("Menu", "control"),
    0x0078: ("Stop", "control"),
    0x007A: ("Undo", "control"),
    0x007B: ("Cut", "control"),
    0x007C: ("Copy", "control"),
    0x007D: ("Paste", "control"),
    0x007E: ("Find", "control"),
})
for i in range(1, 10):
    BASIC[0x0058 + i] = ("KP%d" % i, "control")

for i in range(12):
    BASIC[0x003A + i] = ("F%d" % (i + 1), "fkeys")
for i in range(12):
    BASIC[0x0068 + i] = ("F%d" % (i + 13), "fkeys")

MODS = {
    0x00E0: ("LCtrl", "mods"),
    0x00E1: ("LShft", "mods"),
    0x00E2: ("LAlt", "mods"),
    0x00E3: ("LGui", "mods"),
    0x00E4: ("RCtrl", "mods"),
    0x00E5: ("RShft", "mods"),
    0x00E6: ("RAlt", "mods"),
    0x00E7: ("RGui", "mods"),
}
BASIC.update(MODS)

# медиа-клавиши (Consumer page)
MEDIA = {
    0x00A5: ("WwwBk", "media"),
    0x00A6: ("WwwFw", "media"),
    0x00A7: ("WwwRef", "media"),
    0x00A8: ("Mute", "media"),
    0x00A9: ("Vol+", "media"),
    0x00AA: ("Vol-", "media"),
    0x00AB: ("Next", "media"),
    0x00AC: ("Prev", "media"),
    0x00AD: ("Stop", "media"),
    0x00AE: ("Play", "media"),
    0x00AF: ("Mail", "media"),
    0x00B0: ("Calc", "media"),
    0x00B1: ("MyPC", "media"),
    0x00B4: ("Eject", "media"),
    0x00B5: ("Play", "media"),
    0x00B6: ("MSel", "media"),
    0x00B7: ("MStop", "media"),
    0x00BB: ("MPrev", "media"),
    0x00BC: ("MStop", "media"),
    0x00BD: ("Bri-", "media"),
    0x00BE: ("Bri+", "media"),
}
BASIC.update(MEDIA)

# подсветка (QK_BACKLIGHT / RGB)
LIGHTING = {
    0x7820: "BL+",
    0x7821: "BL-",
    0x7822: "BL↓",
    0x7823: "BL↑",
    0x7824: "BLstep",
    0x7825: "BLtog",
    0x7826: "BLbreath",
    0x7827: "RGB-",
    0x7828: "RGB+",
    0x7829: "RGBtog",
    0x782A: "RGBmode",
    0x782B: "RGBhue+",
    0x782C: "RGBhue-",
    0x782D: "RGBsat+",
    0x782E: "RGBsat-",
    0x782F: "RGBval+",
    0x7830: "RGBval-",
    0x7831: "RGBspd+",
    0x7832: "RGBspd-",
}

# кастомные Keychron (QK_KB_n, база 0x7E00) — порядок из официального definition
KEYCHRON_CUSTOM = [
    "MCtrl", "LPad", "LOpt", "ROpt", "LCmd", "RCmd", "Task", "File",
    "SShot", "Cortana", "Siri", "BTH1", "BTH2", "BTH3", "Batt",
]
for i, nm in enumerate(KEYCHRON_CUSTOM):
    BASIC[0x7E00 + i] = (nm, "keychron")


def describe(kc):
    """Человекочитаемое имя keycode'а."""
    if kc in BASIC:
        return BASIC[kc][0]
    if kc in LIGHTING:
        return LIGHTING[kc]

    hi = (kc >> 8) & 0xFF
    lo = kc & 0xFF

    # QMK quantum-диапазоны слёв (см. quantum/quantum_keycodes.h):
    #   0x5200 | layer  = TO(layer)
    #   0x5220 | layer  = MO(layer)
    #   0x5100 | layer  = DF(layer)
    #   0x5300 | layer  = TG(layer)
    #   0x5280 | layer  = OSL(layer)
    if hi == 0x52:
        if 0x5220 <= kc <= 0x523F:
            return "MO%d" % (kc & 0x1F)
        if 0x5280 <= kc <= 0x529F:
            return "OSL%d" % (kc & 0x1F)
        if 0x5200 <= kc <= 0x521F:
            return "TO%d" % (kc & 0x1F)
        return "QK52_%02X" % lo
    if hi == 0x51:
        return "DF%d" % (lo & 0x1F)
    if hi == 0x53:
        return "TG%d" % (lo & 0x1F)
    if 0x0100 <= kc <= 0x1FFF:
        mod = (kc >> 8) & 0x0F
        base = kc & 0xFF
        names = {1: "Ctrl", 2: "Shft", 3: "Alt", 4: "Gui",
                 5: "RCtrl", 6: "RShft", 7: "RAlt", 8: "RGui"}
        return "%s+%s" % (names.get(mod, "M%d" % mod), describe(base))
    return "%04X" % kc


def category_of(kc):
    if kc in BASIC:
        return BASIC[kc][1]
    if kc in LIGHTING:
        return "lighting"
    return "other"


# --- наборы для палитры ---
def palette():
    """Возвращает словарь: категория -> список (label, keycode)."""
    out = {}

    letters = [(BASIC[0x04 + i][0], 0x04 + i) for i in range(26)]
    letters += [(BASIC[0x1E + i][0], 0x1E + i) for i in range(10)]
    out["Буквы и цифры"] = letters

    sym = [chr(c) for c in range(0x2D, 0x39)]
    sym_labels = ["-", "=", "[", "]", "\\", "#", ";", "'", "`", ",", ".", "/"]
    out["Символы"] = [(sym_labels[i], 0x2D + i) for i in range(len(sym_labels))]

    out["Управление"] = [
        ("Esc", 0x29), ("Tab", 0x2B), ("Caps", 0x39), ("Enter", 0x28),
        ("Space", 0x2C), ("Bksp", 0x2A), ("Del", 0x4C), ("Ins", 0x49),
        ("Home", 0x4A), ("End", 0x4D), ("PgUp", 0x4B), ("PgDn", 0x4E),
        ("PrtSc", 0x46), ("ScrLk", 0x47), ("Pause", 0x48), ("Menu", 0x65),
        ("←", 0x50), ("↓", 0x51), ("↑", 0x52), ("→", 0x4F),
    ]

    out["F-клавиши"] = [("F%d" % i, 0x3A + i - 1) for i in range(1, 13)]
    out["F-клавиши"] += [("F%d" % i, 0x68 + i - 13) for i in range(13, 25)]

    out["Модификаторы"] = [
        ("LCtrl", 0xE0), ("LShft", 0xE1), ("LAlt", 0xE2), ("LGui", 0xE3),
        ("RCtrl", 0xE4), ("RShft", 0xE5), ("RAlt", 0xE6), ("RGui", 0xE7),
    ]

    out["Слои"] = [("▽ TRNS", 0x0001), ("· NO", 0x0000)]
    for l in range(4):
        out["Слои"].append(("MO%d" % l, 0x5200 + l))
    for l in range(4):
        out["Слои"].append(("TG%d" % l, 0x5100 + l))
    for l in range(4):
        out["Слои"].append(("TO%d" % l, 0x5300 + l))
    for l in range(4):
        out["Слои"].append(("OSL%d" % l, 0x5400 + l))

    out["Медиа"] = [
        ("Mute", 0xA8), ("Vol+", 0xA9), ("Vol-", 0xAA),
        ("Play", 0xAE), ("Next", 0xAB), ("Prev", 0xAC), ("Stop", 0xAD),
        ("Bri+", 0xBE), ("Bri-", 0xBD), ("Eject", 0xB4),
    ]

    out["Подсветка"] = [(LIGHTING[k], k) for k in sorted(LIGHTING)]

    out["Keychron"] = [("KB: " + nm, 0x7E00 + i)
                       for i, nm in enumerate(KEYCHRON_CUSTOM)]

    return out
