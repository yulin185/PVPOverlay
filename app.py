# -*- coding: utf-8 -*-
"""
PVP对战信息助手
- 顶部透明置顶横条：双方选手名 / 6 精灵 / 魔力爱心 / 总比分 / 比赛名称
- 控制面板：设置选手、选择精灵、比分、魔力、显示开关
"""
import sys, os, json, csv, ctypes
from PySide6.QtCore import (Qt, QSize, QPoint, QTimer, QAbstractNativeEventFilter,
                            QObject, Signal)
from PySide6.QtGui import (QFont, QFontDatabase, QPixmap, QColor, QPainter,
                           QPainterPath, QBrush, QPen, QIcon, QLinearGradient,
                           QFontMetrics, QImage)
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton,
                               QLineEdit, QHBoxLayout, QVBoxLayout, QGridLayout,
                               QGroupBox, QDialog, QListWidget, QListWidgetItem,
                               QFrame, QSpinBox, QComboBox, QGraphicsDropShadowEffect,
                               QSystemTrayIcon, QMenu, QSlider, QInputDialog,
                               QFileDialog, QMessageBox)

# ----------------------------------------------------------------------------
# 资源路径
# ----------------------------------------------------------------------------
def res_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(base, rel)
    return p

RES = "资源"
FONT_CN = "站酷文艺体"
FONT_NUM = "Bahnschrift"

_pix_cache = {}
def load_pix(path):
    if path not in _pix_cache:
        fp = res_path(os.path.join(RES, path)) if path else ""
        pm = QPixmap(fp) if fp and os.path.exists(fp) else QPixmap()
        _pix_cache[path] = pm
    return _pix_cache[path]

def round_pix(pm, size, border=None):
    """圆形头像，可选主题色光环边框"""
    if pm.isNull():
        pm = QPixmap(size, size); pm.fill(QColor("#5a6378"))
    pm = pm.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    out = QPixmap(size, size); out.fill(Qt.transparent)
    pt = QPainter(out); pt.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath(); path.addEllipse(0, 0, size, size)
    pt.setClipPath(path); pt.drawPixmap(0, 0, pm)
    pt.setClipping(False)
    if border:
        pen = QPen(QColor(border)); pen.setWidth(3)
        pt.setPen(pen); pt.drawEllipse(1, 1, size - 2, size - 2)
    pt.end()
    return out

def grayscale_pix(pm):
    """把 QPixmap 转为灰度"""
    if pm.isNull():
        return pm
    img = pm.toImage().convertToFormat(QImage.Format_Grayscale8)
    return QPixmap.fromImage(img)

def fainted_pix(pm, size):
    """阵亡头像：灰度压暗 + 暗色圆环 + 发光红斜杠"""
    if pm.isNull():
        pm = QPixmap(size, size); pm.fill(QColor("#5a6378"))
    gray = grayscale_pix(pm).scaled(size, size, Qt.KeepAspectRatioByExpanding,
                                    Qt.SmoothTransformation)
    out = QPixmap(size, size); out.fill(Qt.transparent)
    p = QPainter(out); p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath(); path.addEllipse(0, 0, size, size)
    p.setClipPath(path)
    p.drawPixmap(0, 0, gray)
    p.fillRect(0, 0, size, size, QColor(0, 0, 0, 115))          # 压暗
    p.setClipping(False)
    p.setPen(QPen(QColor("#3f4756"), 3)); p.drawEllipse(1, 1, size - 2, size - 2)
    # 艺术性红斜杠：外发光 + 实色芯 + 细高光
    a, b = size * 0.27, size * 0.73
    p.setPen(QPen(QColor(255, 56, 56, 85), 9, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(a, a, b, b)
    p.setPen(QPen(QColor("#ff5252"), 4, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(a, a, b, b)
    p.setPen(QPen(QColor("#ffd0d0"), 1.3, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(a, a, b, b)
    p.end()
    return out

# 主题色
LEFT_THEME = "#22d3ee"    # 青
RIGHT_THEME = "#fb7185"   # 粉红
GOLD = "#fbbf24"

# ----------------------------------------------------------------------------
# 数据
# ----------------------------------------------------------------------------
SPRITES = json.load(open(res_path(os.path.join(RES, "sprites_data.json")),
                       encoding="utf-8"))
SPRITE_BY_KEY = {s["key"]: s for s in SPRITES}

# 编号 / 名称索引（多形态 -> list，用于外部文件容错匹配）
_BY_ID, _BY_NAME = {}, {}
for _s in SPRITES:
    _BY_ID.setdefault(_s["id"], []).append(_s)
    _BY_NAME.setdefault(_s["name"], []).append(_s)

def resolve_sprite(token):
    """把外部文本解析为唯一精灵 key。
    支持：完整 key、编号、名称、编号+名称/形态组合。
    成功返回 (key, None)；无法唯一确定返回 (None, 原因)。空值返回 (None, None)。
    """
    if token is None:
        return None, None
    t = str(token).strip()
    if not t:
        return None, None
    if t in SPRITE_BY_KEY:              # 完整 key
        return t, None
    # 拆出前导编号，如 "001 圣光迪莫"、"416.加尔"
    digits = ""
    for ch in t:
        if ch.isdigit():
            digits += ch
        else:
            break
    body = t[len(digits):].lstrip(" .、-_·:：") if digits else t
    if digits:
        if digits not in _BY_ID:
            return None, f"编号 {digits} 不存在"
        pool = _BY_ID[digits]
        if body:
            exact = [x for x in pool if x["name"] == body]
            if exact:
                pool = exact
            else:
                keyhit = [x for x in pool if body in x["key"]]
                if keyhit:
                    pool = keyhit
        cands = pool
    elif t in _BY_NAME:                 # 名称精确
        cands = _BY_NAME[t]
    else:                               # 名称包含匹配
        cands = [x for x in SPRITES if t in x["name"] or t in x["key"]]
    if not cands:
        return None, f"未找到与「{t}」匹配的精灵"
    if len(cands) == 1:
        return cands[0]["key"], None
    keys = sorted(x["key"] for x in cands)
    shown = "、".join(keys[:5]) + ("..." if len(keys) > 5 else "")
    return None, f"「{t}」匹配到多个形态，请用完整 key 指定: {shown}"

# ----------------------------------------------------------------------------
# 外部预设文件解析（txt / csv / xlsx）
# ----------------------------------------------------------------------------
MAX_PRESET = 500
PRESET_COLUMNS = ["预设名称", "选手名称", "精灵1", "精灵2", "精灵3",
                  "精灵4", "精灵5", "精灵6"]

def _hcell(v):
    return str(v if v is not None else "").strip().replace(" ", "").lower()

def _map_columns(headers):
    """按表头文字定位列，返回 preset/player 列号与精灵槽->列号映射。"""
    loc = {"preset": None, "player": None, "sprite": {}}
    for i, h in enumerate(headers):
        h = _hcell(h)
        if not h:
            continue
        if "选手" in h or "玩家" in h or "player" in h:
            loc["player"] = i
        elif "预设" in h or ("名称" in h and "精灵" not in h) or h == "name":
            loc["preset"] = i
        else:
            for kw in ("精灵", "宠物", "位置", "sprite", "pet"):
                if kw in h:
                    num = "".join(ch for ch in h if ch.isdigit())
                    if num and 0 <= int(num) - 1 < 6:
                        loc["sprite"][int(num) - 1] = i
                    break
    return loc

def _looks_like_header(headers):
    joined = "".join(_hcell(x) for x in headers)
    return any(k in joined for k in ("预设", "精灵", "宠物", "preset", "sprite"))

def _read_text_rows(path):
    raw = open(path, "r", encoding="utf-8-sig").read()
    delim = "\t" if raw.count("\t") > raw.count(",") else ","
    return [row for row in csv.reader(raw.splitlines(), delimiter=delim)]

def _read_xlsx_rows(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.active
    rows = []
    for r in ws.iter_rows(values_only=True):
        rows.append(["" if v is None else str(v) for v in r])
    return rows

def read_preset_rows(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xlsx":
        return _read_xlsx_rows(path)
    if ext in (".txt", ".csv"):
        return _read_text_rows(path)
    raise ValueError(f"不支持的文件类型: {ext}（请使用 .txt/.csv/.xlsx）")

def build_preset_records(rows):
    """把原始文本行解析为预设记录，返回 (records, errors)。
    records=[{name, player, sprites}]；无法解析的精灵置空并在 errors 中说明。"""
    rows = [r for r in rows if any(str(c).strip() for c in r)]
    if not rows:
        return [], ["文件为空或没有有效数据行"]
    first = rows[0]
    has_header = _looks_like_header(first)
    if has_header:
        loc = _map_columns(first); data_rows = rows[1:]; start = 2
    else:
        loc = {"preset": 0, "player": 1,
               "sprite": {i: i + 2 for i in range(6)}}
        data_rows = rows; start = 1
    records, errors = [], []
    for n, row in enumerate(data_rows, start=start):
        def cell(idx):
            return row[idx] if idx is not None and idx < len(row) else ""
        pname = cell(loc["preset"]).strip()
        if not pname:
            errors.append(f"第{n}行：缺少预设名称，已跳过"); continue
        sprites, bad = [None] * 6, []
        for slot, ci in sorted(loc["sprite"].items()):
            key, why = resolve_sprite(cell(ci))
            if why:
                bad.append(f"精灵{slot+1}（{why}）")
            sprites[slot] = key
        if bad:
            errors.append(f"第{n}行「{pname}」：" + "；".join(bad))
        records.append({"name": pname, "player": cell(loc["player"]).strip(),
                        "sprites": sprites})
    return records, errors

def preset_export_rows(items):
    """预设列表 -> 含表头的文本行。"""
    rows = [PRESET_COLUMNS]
    for it in items:
        rows.append([it["name"], ""] + [k or "" for k in it["sprites"]])
    return rows

def write_preset_csv(path, items):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(preset_export_rows(items))

def write_preset_xlsx(path, items):
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "阵容预设"
    for r in preset_export_rows(items):
        ws.append(r)
    wb.save(path)

def export_preset_file(path, items):
    p = path.lower()
    if p.endswith(".xlsx"):
        write_preset_xlsx(path, items)
    elif p.endswith((".txt", ".csv")):
        write_preset_csv(path, items)
    else:
        raise ValueError("仅支持导出 .xlsx/.txt/.csv")

def template_rows():
    """带表头和示例的模板行。"""
    ex = [SPRITES[i]["key"] for i in range(6)]
    return [PRESET_COLUMNS,
            ["示例队伍A", "选手甲"] + ex,
            ["示例队伍B", "选手乙"] + list(reversed(ex))]

def write_template_file(path):
    p = path.lower()
    if p.endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.Workbook(); ws = wb.active; ws.title = "阵容预设"
        for r in template_rows():
            ws.append(r)
        wb.save(path)
    elif p.endswith((".txt", ".csv")):
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerows(template_rows())
    else:
        raise ValueError("模板仅支持 .xlsx/.txt/.csv")

def new_side():
    return {"name": "", "sprites": [None] * 6, "mana": 4, "score": 0,
            "fainted": [False] * 6}

STATE = {"match_name": "闪耀大赛", "show": True,
         "name_history": [],
         "presets": [],
         "opacity": 92,
         "left": new_side(), "right": new_side()}

# ----------------------------------------------------------------------------
# 精灵选择对话框
# ----------------------------------------------------------------------------
class SpritePicker(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择精灵")
        self.setFixedSize(440, 560)
        self.setStyleSheet(POPUP_QSS)
        v = QVBoxLayout(self)
        self.search = QLineEdit(); self.search.setPlaceholderText("输入名称或编号搜索…")
        self.search.textChanged.connect(self.refresh)
        v.addWidget(self.search)
        self.lw = QListWidget(); self.lw.setIconSize(QSize(40, 40))
        self.lw.itemDoubleClicked.connect(self.accept)
        v.addWidget(self.lw)
        row = QHBoxLayout()
        clear = QPushButton("清空"); clear.clicked.connect(self.do_clear)
        ok = QPushButton("确定"); ok.clicked.connect(self.accept)
        cancel = QPushButton("取消"); cancel.clicked.connect(self.reject)
        row.addWidget(clear); row.addStretch(); row.addWidget(ok); row.addWidget(cancel)
        v.addLayout(row)
        self.result_key = None
        self.action = None   # None=取消, "pick"=选择, "clear"=清空
        self.refresh("")
        QTimer.singleShot(50, self.search.setFocus)

    def do_clear(self):
        self.action = "clear"; self.result_key = None
        QDialog.accept(self)

    def refresh(self, text):
        text = text.strip().lower()
        self.lw.clear()
        for s in SPRITES:
            if text and text not in s["name"].lower() and text not in s["id"]:
                continue
            it = QListWidgetItem(f"  {s['id']}  {s['name']}")
            pm = round_pix(load_pix(s["avatar"]), 40)
            it.setIcon(QIcon(pm))
            it.setData(Qt.UserRole, s["key"])
            self.lw.addItem(it)

    def accept(self):
        it = self.lw.currentItem()
        if it is not None:
            self.result_key = it.data(Qt.UserRole); self.action = "pick"
        QDialog.accept(self)

# ----------------------------------------------------------------------------
# 横条内单个精灵
# ----------------------------------------------------------------------------
class SpriteChip(QWidget):
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setFixedWidth(64)
        v = QVBoxLayout(self); v.setContentsMargins(1, 1, 1, 1); v.setSpacing(1)
        self.avatar = QLabel(); self.avatar.setFixedSize(48, 48); self.avatar.setAlignment(Qt.AlignCenter)
        self.name = QLabel(); self.name.setFixedWidth(62); self.name.setAlignment(Qt.AlignCenter)
        self.name.setFont(QFont(FONT_CN, 9))
        self.name.setStyleSheet("color:#e8ecf5; background:transparent;")
        self.types = QLabel(); self.types.setAlignment(Qt.AlignCenter)
        self.types.setStyleSheet("background:transparent;")
        v.addWidget(self.avatar, 0, Qt.AlignHCenter)
        v.addWidget(self.name, 0, Qt.AlignHCenter)
        v.addWidget(self.types, 0, Qt.AlignHCenter)
        self.set_key(None)

    def _fit_name(self, text):
        """名字超宽时逐档缩字号，保证在标签宽度内完整、居中显示。"""
        size = 9
        font = QFont(FONT_CN, size)
        while QFontMetrics(font).horizontalAdvance(text) > self.name.width() and size > 6:
            size -= 1
            font = QFont(FONT_CN, size)
        self.name.setFont(font)

    def set_key(self, key, fainted=False):
        s = SPRITE_BY_KEY.get(key)
        if not s:
            self.avatar.setPixmap(round_pix(QPixmap(), 48))
            self.name.setFont(QFont(FONT_CN, 9))
            self.name.setStyleSheet("color:#e8ecf5; background:transparent;")
            self.name.setText("—"); self.types.setText(""); return
        if fainted:
            self.avatar.setPixmap(fainted_pix(load_pix(s["avatar"]), 48))
            self.name.setStyleSheet("color:#8b93a5; background:transparent;")
        else:
            self.avatar.setPixmap(round_pix(load_pix(s["avatar"]), 48, self.theme))
            self.name.setStyleSheet("color:#e8ecf5; background:transparent;")
        self._fit_name(s["name"])
        self.name.setText(s["name"])
        # 系别小图标（阵亡时灰度化）
        tps = []
        for t in s["types"]:
            tp = load_pix(os.path.join("type_icons", f"{t}系图标.png"))
            if not tp.isNull():
                tp = tp.scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                if fainted:
                    tp = grayscale_pix(tp)
                tps.append(tp)
        if tps:
            w = 16 * len(tps) + 2 * (len(tps) - 1)
            canvas = QPixmap(w, 16); canvas.fill(Qt.transparent)
            p = QPainter(canvas); x = 0
            for tp in tps:
                p.drawPixmap(x, 0, tp); x += 18
            p.end(); self.types.setPixmap(canvas)

# 爱心
class Hearts(QWidget):
    def __init__(self, theme, parent=None):
        super().__init__(parent); self.theme = theme
        self.mana = 4
        self.setFixedSize(96, 26)
    def set_mana(self, m):
        self.mana = m; self.update()
    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        f = QFont(FONT_NUM); f.setPixelSize(22); f.setBold(True); p.setFont(f)
        for i in range(4):
            color = QColor("#22c55e") if i < self.mana else QColor("#3a3f4d")
            p.setPen(color)
            p.drawText(QPoint(2 + i * 24, 21), "♥")
        p.end()

# ----------------------------------------------------------------------------
# 悬浮横条
# ----------------------------------------------------------------------------
class OverlayBar(QWidget):
    H = 98
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                            Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._drag = None
        self.build()
        hint = self.layout().sizeHint()
        self.resize(hint.width(), self.H)
        self.center_on_top()
        self.setWindowOpacity(STATE["opacity"] / 100.0)

    def apply_opacity(self):
        self.setWindowOpacity(STATE["opacity"] / 100.0)

    def center_on_top(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.x() + (screen.width() - self.width()) // 2
        self.move(x, 0)

    def build(self):
        root = QHBoxLayout(self); root.setContentsMargins(12, 6, 12, 6); root.setSpacing(0)
        # 两侧精灵
        self.left = self._make_chips(LEFT_THEME, False)
        self.right = self._make_chips(RIGHT_THEME, True)
        root.addWidget(self.left["box"])
        # 左玩家块（名字在上、爱心在下）
        root.addWidget(self._player_block(self.left))
        # 中间比赛信息
        center = QVBoxLayout(); center.setSpacing(0)
        self.match_label = QLabel("闪耀大赛"); self.match_label.setAlignment(Qt.AlignCenter)
        self.match_label.setFont(QFont(FONT_CN, 14, QFont.Bold))
        self.match_label.setStyleSheet("color:#f1f5ff; background:transparent;")
        self.score_label = QLabel(); self.score_label.setAlignment(Qt.AlignCenter)
        self.score_label.setFont(QFont(FONT_NUM, 30, QFont.Bold))
        self.score_label.setStyleSheet("background:transparent;")
        center.addStretch(); center.addWidget(self.match_label)
        center.addWidget(self.score_label); center.addStretch()
        cw = QWidget(); cw.setFixedWidth(220); cw.setLayout(center); cw.setAttribute(Qt.WA_TranslucentBackground)
        root.addSpacing(10); root.addWidget(cw); root.addSpacing(10)
        # 右玩家块
        root.addWidget(self._player_block(self.right))
        root.addWidget(self.right["box"])

    def _make_chips(self, theme, rtl):
        lay = QHBoxLayout(); lay.setSpacing(0)
        chip_list = []
        for i in range(6):
            c = SpriteChip(theme); chip_list.append(c); lay.addWidget(c)
        if rtl:
            lay.setDirection(QHBoxLayout.RightToLeft)
        box = QWidget(); box.setLayout(lay); box.setAttribute(Qt.WA_TranslucentBackground)
        return {"box": box, "chips": chip_list, "theme": theme}

    def _player_block(self, side):
        theme = side["theme"]
        name = QLabel("选手"); name.setAlignment(Qt.AlignCenter)
        name.setFont(QFont(FONT_CN, 13, QFont.Bold))
        name.setStyleSheet(f"color:{theme}; background:transparent;")
        glow = QGraphicsDropShadowEffect(name); glow.setColor(QColor(theme))
        glow.setBlurRadius(14); glow.setOffset(0); name.setGraphicsEffect(glow)
        hearts = Hearts(theme)
        v = QVBoxLayout(); v.setSpacing(2)
        v.addStretch(); v.addWidget(name)
        v.addWidget(hearts, 0, Qt.AlignCenter); v.addStretch()
        block = QWidget(); block.setFixedWidth(104); block.setLayout(v)
        block.setAttribute(Qt.WA_TranslucentBackground)
        side["name"] = name; side["hearts"] = hearts
        return block


    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(8, 4, -8, -4)
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0, QColor(10, 16, 32, 225))
        grad.setColorAt(0.5, QColor(16, 20, 40, 235))
        grad.setColorAt(1, QColor(10, 16, 32, 225))
        path = QPainterPath(); path.addRoundedRect(r, 18, 18)
        p.fillPath(path, QBrush(grad))
        pg = QLinearGradient(0, 0, self.width(), 0)
        pg.setColorAt(0, QColor(LEFT_THEME)); pg.setColorAt(0.5, QColor(GOLD)); pg.setColorAt(1, QColor(RIGHT_THEME))
        p.setPen(QPen(QBrush(pg), 2)); p.drawPath(path)
        p.end()

    def render_state(self):
        self.match_label.setText(STATE["match_name"] or "闪耀大赛")
        sl, sr = STATE["left"], STATE["right"]
        self.score_label.setText(
            f'<span style="color:{LEFT_THEME}">{sl["score"]}</span>'
            '<span style="color:#94a3b8"> : </span>'
            f'<span style="color:{RIGHT_THEME}">{sr["score"]}</span>')
        self.score_label.setTextFormat(Qt.RichText)
        for side, data in ((self.left, sl), (self.right, sr)):
            side["name"].setText(data["name"] or "选手")
            side["hearts"].set_mana(data["mana"])
            for i, chip in enumerate(side["chips"]):
                chip.set_key(data["sprites"][i], data["fainted"][i])

    # 拖动
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)
    def mouseReleaseEvent(self, e):
        self._drag = None

# ----------------------------------------------------------------------------
# 全局热键：Ctrl+Alt+H 显示/隐藏悬浮条（无需切出当前应用）
# ----------------------------------------------------------------------------
WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x4000
HK_ID = 0xC01

class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, cb):
        super().__init__()
        self.cb = cb
    def nativeEventFilter(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            try:
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and msg.wParam == HK_ID:
                    self.cb()
                    return True, 0
            except Exception:
                pass
        return False, 0

class HotkeyManager(QObject):
    triggered = Signal()
    def __init__(self, app):
        super().__init__()
        self.ok = False
        self.filter = None
        try:
            import ctypes.wintypes  # noqa
            u = ctypes.windll.user32
            self.ok = bool(u.RegisterHotKey(None, HK_ID,
                        MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord("H")))
            # 必须保持过滤器引用，否则会被垃圾回收导致热键失效
            self.filter = HotkeyFilter(self.triggered.emit)
            app.installNativeEventFilter(self.filter)
        except Exception as ex:
            print("热键注册失败:", ex)

# ----------------------------------------------------------------------------
# 控制面板
# ----------------------------------------------------------------------------
PANEL_QSS = """
QWidget { background:#0d1322; color:#e8ecf5; font-size:13px; }
QGroupBox { border:1px solid #28304a; border-radius:10px; margin-top:14px;
            padding:8px; font-weight:bold; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 4px; color:#9fb2d4; }
QLineEdit, QSpinBox { background:#161d33; border:1px solid #2c3656; border-radius:6px;
                      padding:5px; }
QPushButton { background:#243055; border:1px solid #3a4a78; border-radius:6px;
              padding:6px 10px; }
QPushButton:hover { background:#33447a; }
QPushButton#slot { text-align:left; padding:8px; }
QPushButton#faint { padding:6px 4px; font-weight:bold; color:#c7d0e2; }
QPushButton#faint:disabled { color:#525c72; background:#1a2136; border-color:#262f47; }
QPushButton#faint:checked { background:#b02a2a; border-color:#ff5252; color:#ffffff; }
QPushButton#faint:checked:hover { background:#c93434; }
QPushButton#toggle_on { background:#0f5132; border-color:#198754; }
QPushButton#toggle_off { background:#5c2a2a; border-color:#843a3a; }
"""
POPUP_QSS = """
QWidget { background:#0d1322; color:#e8ecf5; }
QLineEdit { background:#161d33; border:1px solid #2c3656; border-radius:6px; padding:6px;}
QListWidget { background:#121a30; border:1px solid #2c3656; border-radius:8px;}
QListWidget::item { padding:6px; border-radius:6px;}
QListWidget::item:selected { background:#2c4a8a;}
QPushButton { background:#243055; border:1px solid #3a4a78; border-radius:6px; padding:6px 12px;}
QPushButton:hover { background:#33447a;}
"""

class NameCombo(QComboBox):
    """可编辑下拉：输入过的选手名自动记忆，下拉底部可清空历史。"""
    CLEAR = "✕ 清空历史记录"

    def __init__(self, side_key, set_name, on_history_changed=None):
        super().__init__()
        self.side_key = side_key
        self.set_name_cb = set_name
        self.on_history_changed = on_history_changed
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMinimumWidth(180)
        self.lineEdit().setPlaceholderText("输入或选择选手名称")
        self.reload_items()
        self.editTextChanged.connect(self.on_edit)
        self.currentIndexChanged.connect(self.on_pick)
        self.lineEdit().editingFinished.connect(self.remember)

    def reload_items(self):
        self.blockSignals(True)
        self.clear()
        self.addItems(STATE["name_history"])
        if STATE["name_history"]:
            self.insertSeparator(len(STATE["name_history"]))
        self.addItem(self.CLEAR)
        self.blockSignals(False)

    def on_edit(self, text):
        self.set_name_cb(self.side_key, text)

    def on_pick(self, idx):
        if self.itemText(idx) == self.CLEAR:
            STATE["name_history"] = []
            self.reload_items()
            self.setCurrentText("")   # 触发 on_edit，清空选手名
            if self.on_history_changed:
                self.on_history_changed()

    def remember(self):
        t = self.currentText().strip()
        if t and t != self.CLEAR and t not in STATE["name_history"]:
            STATE["name_history"].insert(0, t)
            STATE["name_history"] = STATE["name_history"][:50]
            self.reload_items()
            self.setCurrentText(t)
            if self.on_history_changed:
                self.on_history_changed()

class SlotButton(QPushButton):
    def __init__(self, idx, side_key, refresh):
        super().__init__(f"{idx+1}. 未选择")
        self.idx, self.side_key, self.refresh = idx, side_key, refresh
        self.setObjectName("slot"); self.setMinimumWidth(180)
        self.clicked.connect(self.pick)
    def pick(self):
        dlg = SpritePicker()
        dlg.exec()
        if dlg.action == "clear":
            STATE[self.side_key]["sprites"][self.idx] = None
            STATE[self.side_key]["fainted"][self.idx] = False
        elif dlg.action == "pick":
            STATE[self.side_key]["sprites"][self.idx] = dlg.result_key
            STATE[self.side_key]["fainted"][self.idx] = False
        self.refresh()
    def update_text(self):
        key = STATE[self.side_key]["sprites"][self.idx]
        s = SPRITE_BY_KEY.get(key)
        mark = "✕ " if STATE[self.side_key]["fainted"][self.idx] else ""
        if s:
            self.setText(f"{mark}{self.idx+1}. {s['id']} {s['name']}")
        else:
            self.setText(f"{self.idx+1}. 未选择")

class ControlPanel(QWidget):
    def __init__(self, overlay):
        super().__init__()
        self.overlay = overlay
        self.setWindowTitle("PVP对战信息助手 - 控制面板")
        self.setStyleSheet(PANEL_QSS)
        self.setFont(QFont(FONT_CN, 10))
        self.setMinimumWidth(860)
        v = QVBoxLayout(self)
        # 第一行：显示开关 / 比赛名称 / 快捷操作
        top = QHBoxLayout()
        self.toggle = QPushButton(); self.toggle.clicked.connect(self.toggle_show)
        match_lab = QLabel("比赛名称:")
        self.match_edit = QLineEdit(STATE["match_name"]); self.match_edit.setMinimumWidth(160)
        self.match_edit.textChanged.connect(self.on_change)
        top.addWidget(self.toggle); top.addSpacing(14)
        top.addWidget(match_lab); top.addWidget(self.match_edit)
        new_game = QPushButton("新小局·魔力回满"); new_game.clicked.connect(self.new_round)
        reset_score = QPushButton("比分清零"); reset_score.clicked.connect(self.reset_scores)
        top.addSpacing(12); top.addWidget(new_game); top.addWidget(reset_score)
        top.addStretch()
        v.addLayout(top)
        # 第二行：透明度 / 热键提示
        opt = QHBoxLayout()
        opt.addWidget(QLabel("透明度:"))
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(30, 100); self.opacity_slider.setFixedWidth(150)
        self.opacity_slider.setValue(STATE["opacity"])
        self.opacity_slider.valueChanged.connect(self.set_opacity)
        self.opacity_val = QLabel(f"{STATE['opacity']}%")
        opt.addWidget(self.opacity_slider); opt.addWidget(self.opacity_val); opt.addSpacing(16)
        hk_lab = QLabel("全局热键 Ctrl+Alt+H 一键显示/隐藏")
        hk_lab.setStyleSheet("color:#9fb2d4;")
        opt.addWidget(hk_lab); opt.addStretch()
        v.addLayout(opt)
        # 左右
        sides = QHBoxLayout()
        self.slot_buttons = []
        self.faint_buttons = []
        sides.addWidget(self._build_side("left", "左侧选手", LEFT_THEME), 1)
        sides.addWidget(self._build_side("right", "右侧选手", RIGHT_THEME), 1)
        v.addLayout(sides)
        self.refresh(); self.update_toggle(); self.reload_presets()

    def _build_side(self, key, title, theme):
        gb = QGroupBox(title); gb.setStyleSheet(
            f"QGroupBox {{ border:1px solid {theme}; border-radius:10px; margin-top:14px;"
            " padding:8px; font-weight:bold; }")
        outer = QVBoxLayout(gb)
        row = QHBoxLayout()
        row.addWidget(QLabel("选手名:"))
        name_combo = NameCombo(key, self.set_name, self.reload_all_names)
        row.addWidget(name_combo)
        outer.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("总比分:"))
        score = QSpinBox(); score.setRange(0, 99); score.setFixedWidth(64)
        score.valueChanged.connect(lambda val, k=key: self.set_score(k, val))
        row2.addWidget(score)
        for lab, d in (("比分-1", -1), ("比分+1", 1)):
            sb = QPushButton(lab); sb.setFixedWidth(64)
            sb.clicked.connect(lambda _, k=key, d=d: self.bump_score(k, d))
            row2.addWidget(sb)
        row2.addSpacing(8)
        row2.addWidget(QLabel("魔力:"))
        for label, delta in (("−", -1), ("+", 1)):
            b = QPushButton(label); b.setFixedWidth(34)
            b.clicked.connect(lambda _, k=key, d=delta: self.bump_mana(k, d))
            row2.addWidget(b)
        row2.addStretch()
        outer.addLayout(row2)
        # 6 槽
        grid = QGridLayout()
        for i in range(6):
            cell = QWidget(); cl = QHBoxLayout(cell)
            cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(4)
            sb = SlotButton(i, key, self.refresh)
            fb = QPushButton("阵亡"); fb.setFixedWidth(50); fb.setCheckable(True)
            fb.setObjectName("faint"); fb.side_key = key; fb.idx = i
            fb.clicked.connect(lambda _, k=key, i=i: self.toggle_faint(k, i))
            cl.addWidget(sb); cl.addWidget(fb)
            self.slot_buttons.append(sb); self.faint_buttons.append(fb)
            grid.addWidget(cell, i // 2, i % 2)
        outer.addLayout(grid)
        # 阵容预设
        prow = QHBoxLayout()
        prow.addWidget(QLabel("预设:"))
        preset_combo = QComboBox(); preset_combo.setMinimumWidth(110)
        prow.addWidget(preset_combo)
        apply_b = QPushButton("应用"); apply_b.clicked.connect(lambda _, k=key: self.apply_preset(k))
        save_b = QPushButton("保存当前"); save_b.clicked.connect(lambda _, k=key: self.save_preset(k))
        del_b = QPushButton("删除"); del_b.clicked.connect(lambda _, k=key: self.delete_preset(k))
        prow.addWidget(apply_b); prow.addWidget(save_b); prow.addWidget(del_b)
        outer.addLayout(prow)
        # 外部文件：导入 / 导出 / 模板
        irow = QHBoxLayout()
        imp_b = QPushButton("导入文件"); imp_b.clicked.connect(self.import_presets)
        exp_b = QPushButton("导出文件"); exp_b.clicked.connect(self.export_presets)
        tpl_b = QPushButton("导入模板"); tpl_b.clicked.connect(self.save_template)
        irow.addWidget(imp_b); irow.addWidget(exp_b); irow.addWidget(tpl_b)
        irow.addStretch()
        outer.addLayout(irow)
        # 保存引用
        if not hasattr(self, "edits"): self.edits = {}
        self.edits[key] = {"name": name_combo, "score": score, "preset": preset_combo}
        return gb

    def set_name(self, k, t):
        STATE[k]["name"] = t; self.refresh()
    def set_score(self, k, val):
        STATE[k]["score"] = val; self.refresh()
    def bump_mana(self, k, d):
        m = max(0, min(4, STATE[k]["mana"] + d))
        STATE[k]["mana"] = m; self.refresh()

    def toggle_faint(self, k, i):
        side = STATE[k]
        if not side["sprites"][i]:
            return  # 空槽不能标记阵亡
        side["fainted"][i] = not side["fainted"][i]
        d = -1 if side["fainted"][i] else 1
        side["mana"] = max(0, min(4, side["mana"] + d))
        self.refresh()

    def bump_score(self, k, d):
        STATE[k]["score"] = max(0, min(99, STATE[k]["score"] + d)); self.refresh()

    def new_round(self):
        STATE["left"]["mana"] = 4; STATE["right"]["mana"] = 4
        STATE["left"]["fainted"] = [False] * 6
        STATE["right"]["fainted"] = [False] * 6
        self.refresh()

    def reset_scores(self):
        STATE["left"]["score"] = 0; STATE["right"]["score"] = 0; self.refresh()

    def set_opacity(self, val):
        val = max(30, min(100, int(val)))
        STATE["opacity"] = val; self.opacity_val.setText(f"{val}%")
        self.overlay.apply_opacity()

    # ---- 阵容预设（左右共享同一列表）----
    def save_preset(self, k):
        name, ok = QInputDialog.getText(self, "保存阵容预设", "预设名称:")
        name = name.strip()
        if not ok or not name:
            return
        items = [it for it in STATE["presets"] if it["name"] != name]
        items.insert(0, {"name": name, "sprites": list(STATE[k]["sprites"])})
        STATE["presets"] = items[:MAX_PRESET]
        self.reload_presets()

    def apply_preset(self, k):
        combo = self.edits[k]["preset"]
        idx = combo.currentIndex()
        if idx < 0 or idx >= len(STATE["presets"]):
            return
        pres = STATE["presets"][idx]
        STATE[k]["sprites"] = list(pres["sprites"])
        STATE[k]["fainted"] = [False] * 6
        self.refresh()

    def delete_preset(self, k):
        combo = self.edits[k]["preset"]
        idx = combo.currentIndex()
        if idx < 0 or idx >= len(STATE["presets"]):
            return
        del STATE["presets"][idx]
        self.reload_presets()

    def reload_presets(self):
        for k, w in self.edits.items():
            combo = w["preset"]
            combo.blockSignals(True); combo.clear()
            combo.addItems([it["name"] for it in STATE["presets"]])
            combo.blockSignals(False)

    def _remember_name(self, t):
        t = t.strip()
        if t and t not in STATE["name_history"]:
            STATE["name_history"].insert(0, t)
            STATE["name_history"] = STATE["name_history"][:50]

    def import_presets(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入阵容预设", "",
            "预设文件 (*.txt *.csv *.xlsx);;所有文件 (*)")
        if not path:
            return
        try:
            rows = read_preset_rows(path)
        except Exception as ex:
            QMessageBox.warning(self, "导入失败", str(ex)); return
        records, errors = build_preset_records(rows)
        if not records:
            QMessageBox.warning(self, "导入结果",
                "没有可导入的预设。\n" + "\n".join(errors[:10])); return
        new_names = {r["name"] for r in records}
        leftovers = [it for it in STATE["presets"] if it["name"] not in new_names]
        merged = [{"name": r["name"], "sprites": r["sprites"]} for r in records]
        old = {it["name"] for it in STATE["presets"]}
        added = sum(1 for r in records if r["name"] not in old)
        updated = len(records) - added
        final = merged + leftovers
        truncated = len(final) - MAX_PRESET
        if truncated > 0:
            final = final[:MAX_PRESET]
        STATE["presets"] = final
        for r in records:
            self._remember_name(r["player"])
        self.reload_presets(); self.reload_all_names()
        msg = f"成功导入 {len(records)} 条（新增 {added}，覆盖 {updated}），当前共 {len(final)} 条。"
        if truncated > 0:
            msg += f"\n已达上限 {MAX_PRESET}，末尾 {truncated} 条未保留。"
        if errors:
            msg += "\n\n以下问题需注意：\n" + "\n".join(errors[:12])
            if len(errors) > 12:
                msg += f"\n…等共 {len(errors)} 条"
        QMessageBox.information(self, "导入完成", msg)

    def export_presets(self):
        if not STATE["presets"]:
            QMessageBox.information(self, "导出", "当前没有可导出的预设。"); return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出阵容预设", "阵容预设导出.xlsx",
            "Excel 文件 (*.xlsx);;文本文件 (*.txt);;CSV 文件 (*.csv)")
        if not path:
            return
        try:
            export_preset_file(path, STATE["presets"])
        except Exception as ex:
            QMessageBox.warning(self, "导出失败", str(ex)); return
        QMessageBox.information(self, "导出完成",
            f"已导出 {len(STATE['presets'])} 条预设到：\n{path}")

    def save_template(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存导入模板", "阵容预设导入模板.xlsx",
            "Excel 文件 (*.xlsx);;文本文件 (*.txt);;CSV 文件 (*.csv)")
        if not path:
            return
        try:
            write_template_file(path)
        except Exception as ex:
            QMessageBox.warning(self, "模板保存失败", str(ex)); return
        QMessageBox.information(self, "模板已保存",
            "模板含表头和 2 行示例，按格式填写后即可导入。\n" + path)

    def reload_all_names(self):
        # 同步其它选手名下拉的历史列表（保留各自当前文本）
        for k, w in self.edits.items():
            combo = w["name"]; cur = combo.currentText()
            combo.reload_items(); combo.setCurrentText(cur)

    def on_change(self):
        STATE["match_name"] = self.match_edit.text(); self.refresh()

    def toggle_show(self):
        STATE["show"] = not STATE["show"]; self.update_toggle(); self.refresh()

    def update_toggle(self):
        if STATE["show"]:
            self.toggle.setText("● 横条显示中（点击隐藏）"); self.toggle.setObjectName("toggle_on")
        else:
            self.toggle.setText("○ 横条已隐藏（点击显示）"); self.toggle.setObjectName("toggle_off")
        self.toggle.style().unpolish(self.toggle); self.toggle.style().polish(self.toggle)

    def refresh(self):
        self.overlay.render_state()
        self.overlay.setVisible(STATE["show"])
        for sb in self.slot_buttons:
            sb.update_text()
        for fb in self.faint_buttons:
            side = STATE[fb.side_key]
            has = bool(side["sprites"][fb.idx])
            fb.setEnabled(has)
            fb.blockSignals(True)
            fb.setChecked(has and side["fainted"][fb.idx])
            fb.blockSignals(False)
        for k, w in self.edits.items():
            if w["name"].currentText() != STATE[k]["name"]:
                w["name"].setCurrentText(STATE[k]["name"])
            if w["score"].value() != STATE[k]["score"]:
                w["score"].setValue(STATE[k]["score"])

    def closeEvent(self, e):
        # 关闭按钮仅隐藏面板，程序在系统托盘继续运行
        e.ignore(); self.hide()

    def show_from_tray(self):
        self.show(); self.raise_(); self.activateWindow()

# ----------------------------------------------------------------------------
def config_path():
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "config.json")

def load_config():
    p = config_path()
    if not os.path.exists(p):
        return
    try:
        cfg = json.load(open(p, encoding="utf-8"))
        STATE["match_name"] = cfg.get("match_name", STATE["match_name"])
        hist = cfg.get("name_history", [])
        STATE["name_history"] = [str(x) for x in hist if str(x).strip()][:50]
        op = int(cfg.get("opacity", 92))
        STATE["opacity"] = max(30, min(100, op))
        def clean_preset(it):
            sp = it.get("sprites", [])
            sp6 = [sp[i] if i < len(sp) and sp[i] in SPRITE_BY_KEY else None
                   for i in range(6)]
            nm = str(it.get("name", "")).strip()
            return {"name": nm, "sprites": sp6} if nm else None

        ps = cfg.get("presets", [])
        merged = []
        if isinstance(ps, list):
            for it in ps:
                c = clean_preset(it)
                if c and c["name"] not in [x["name"] for x in merged]:
                    merged.append(c)
        elif isinstance(ps, dict):
            # 兼容旧版左右分离结构，迁移合并为共享列表
            for old_k in ("left", "right"):
                for it in ps.get(old_k, []):
                    c = clean_preset(it)
                    if c and c["name"] not in [x["name"] for x in merged]:
                        merged.append(c)
        STATE["presets"] = merged[:30]
        for k in ("left", "right"):
            if k not in cfg:
                continue
            side = cfg[k]
            STATE[k]["name"] = side.get("name", "")
            STATE[k]["score"] = int(side.get("score", 0))
            STATE[k]["mana"] = max(0, min(4, int(side.get("mana", 4))))
            sp = side.get("sprites", [])
            STATE[k]["sprites"] = [sp[i] if i < len(sp) and sp[i] in SPRITE_BY_KEY
                                   else None for i in range(6)]
            ft = side.get("fainted", [])
            # 清洗为布尔、长度补齐；空槽不允许阵亡
            STATE[k]["fainted"] = [bool(ft[i]) if i < len(ft)
                                   and STATE[k]["sprites"][i] else False
                                   for i in range(6)]
    except Exception as ex:
        print("配置加载失败:", ex)

def save_config():
    try:
        json.dump(STATE, open(config_path(), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    except Exception as ex:
        print("配置保存失败:", ex)

def make_tray(app, panel):
    icon = QIcon(res_path(os.path.join(RES, "logo.ico")))
    tray = QSystemTrayIcon(icon)
    tray.setToolTip("PVP对战信息助手")
    menu = QMenu()
    act_toggle = menu.addAction("显示/隐藏悬浮条")
    act_panel = menu.addAction("打开控制面板")
    menu.addSeparator()
    act_quit = menu.addAction("退出")
    tray.setContextMenu(menu)

    def do_toggle():
        STATE["show"] = not STATE["show"]
        panel.update_toggle(); panel.refresh()
    act_toggle.triggered.connect(do_toggle)
    act_panel.triggered.connect(panel.show_from_tray)
    act_quit.triggered.connect(lambda: (save_config(), app.quit()))
    tray.activated.connect(lambda r: do_toggle()
                           if r == QSystemTrayIcon.DoubleClick else None)
    tray.show()
    return tray

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)   # 窗口隐藏后托盘继续运行
    QFontDatabase.addApplicationFont(res_path(os.path.join(RES, "fonts", "站酷文艺体.ttf")))
    QFontDatabase.addApplicationFont(res_path(os.path.join(RES, "bahnschrift.ttf")))
    load_config()
    overlay = OverlayBar()
    panel = ControlPanel(overlay)
    overlay.render_state(); overlay.setVisible(STATE["show"])
    panel.show()

    # 全局热键
    hk = HotkeyManager(app)
    def hk_toggle():
        STATE["show"] = not STATE["show"]
        panel.update_toggle(); panel.refresh()
    hk.triggered.connect(hk_toggle)

    tray = make_tray(app, panel)
    app.aboutToQuit.connect(save_config)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
