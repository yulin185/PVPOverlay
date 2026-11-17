# -*- coding: utf-8 -*-
"""offscreen 无头逻辑测试：验证数据层与组件方法，不污染真实 config.json。"""
import os, sys, json, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as A
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
keys = [s["key"] for s in A.SPRITES]
assert len(keys) >= 6
PASS, FAIL = [], []

def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name)

# 用临时 config 隔离真实配置
tmp = tempfile.mkdtemp()
A.config_path = lambda: os.path.join(tmp, "config.json")

# ---- 实例化 ----
ov = A.OverlayBar()
panel = A.ControlPanel(ov)

# 1. 比分增减
panel.bump_score("left", 1); panel.bump_score("left", 1)
check("比分+1两次 -> 2", A.STATE["left"]["score"] == 2)
panel.bump_score("left", -1)
check("比分-1 -> 1", A.STATE["left"]["score"] == 1)
panel.bump_score("left", -5)
check("比分不会低于0", A.STATE["left"]["score"] == 0)

# 2. 魔力增减与边界
panel.bump_mana("right", -2)
check("魔力-2 -> 2", A.STATE["right"]["mana"] == 2)
panel.bump_mana("right", -5)
check("魔力不会低于0", A.STATE["right"]["mana"] == 0)
panel.bump_mana("right", 9)
check("魔力不会高于4", A.STATE["right"]["mana"] == 4)

# 3. 新小局：魔力回满（比分保留）
A.STATE["left"]["mana"] = 1; A.STATE["right"]["mana"] = 2
A.STATE["left"]["score"] = 3
panel.new_round()
check("新小局双方魔力回满",
      A.STATE["left"]["mana"] == 4 and A.STATE["right"]["mana"] == 4)
check("新小局比分保留", A.STATE["left"]["score"] == 3)

# 4. 比分清零
panel.reset_scores()
check("比分清零", A.STATE["left"]["score"] == 0 and A.STATE["right"]["score"] == 0)

# 5. 透明度
panel.set_opacity(55)
check("透明度STATE更新", A.STATE["opacity"] == 55)
check("悬浮条opacity同步", abs(ov.windowOpacity() - 0.55) < 0.001)
check("透明度标签", panel.opacity_val.text() == "55%")
panel.set_opacity(120)
check("透明度上限保护", A.STATE["opacity"] == 100)

# 6. 共享预设：保存/应用/删除/同名覆盖/左右同步
A.STATE["presets"] = []
A.STATE["left"]["sprites"] = list(keys[:6])
A.QInputDialog.getText = staticmethod(lambda *a, **k: ("我的预设", True))
panel.save_preset("left")
check("预设保存1个", len(A.STATE["presets"]) == 1)
check("预设内容正确", A.STATE["presets"][0]["sprites"] == list(keys[:6]))
check("右侧下拉同步看到预设",
      panel.edits["right"]["preset"].count() == 1
      and panel.edits["right"]["preset"].itemText(0) == "我的预设")
# 改名当前阵容再保存第二个
A.STATE["left"]["sprites"] = list(keys[10:16])
A.QInputDialog.getText = staticmethod(lambda *a, **k: ("第二套", True))
panel.save_preset("left")
check("预设保存2个", len(A.STATE["presets"]) == 2)
# 右侧应用第二个共享预设
panel.edits["right"]["preset"].setCurrentIndex(0)
panel.apply_preset("right")
check("右侧应用共享预设", A.STATE["right"]["sprites"] == list(keys[10:16]))
# 左侧应用第一个
panel.edits["left"]["preset"].setCurrentIndex(1)
panel.apply_preset("left")
check("左侧应用预设恢复阵容", A.STATE["left"]["sprites"] == list(keys[:6]))
# 同名覆盖
A.QInputDialog.getText = staticmethod(lambda *a, **k: ("我的预设", True))
panel.save_preset("left")
check("同名覆盖不增加数量", len(A.STATE["presets"]) == 2)
# 删除
panel.edits["left"]["preset"].setCurrentIndex(0)
panel.delete_preset("left")
check("删除后剩1个", len(A.STATE["presets"]) == 1)
check("删除后两侧下拉同步",
      panel.edits["left"]["preset"].count() == 1
      and panel.edits["right"]["preset"].count() == 1)

# 7. 预设上限（MAX_PRESET）
A.STATE["presets"] = []
for i in range(A.MAX_PRESET + 5):
    A.QInputDialog.getText = staticmethod(lambda *a, _i=i, **k: (f"P{_i}", True))
    panel.save_preset("right")
check(f"预设上限{ A.MAX_PRESET}", len(A.STATE["presets"]) == A.MAX_PRESET)

# 8. 精灵选择器 action 标志
sp = A.SpritePicker()
check("选择器初始action为None", sp.action is None)
sp.do_clear()
check("清空action=clear", sp.action == "clear" and sp.result_key is None)
sp2 = A.SpritePicker(); sp2.lw.setCurrentRow(0); sp2.accept()
check("选择action=pick", sp2.action == "pick" and sp2.result_key == keys[0])

# 9. 配置保存/加载往返
A.STATE["left"]["sprites"] = list(keys[:6]); A.STATE["opacity"] = 77
A.save_config()
check("配置文件已写出", os.path.exists(A.config_path()))
# 重置 STATE 后重新加载
A.STATE["left"]["sprites"] = [None] * 6; A.STATE["opacity"] = 92
A.load_config()
check("配置往返精灵恢复", A.STATE["left"]["sprites"] == list(keys[:6]))
check("配置往返透明度恢复", A.STATE["opacity"] == 77)

# 10. 坏配置不崩溃（脏 key 被过滤）
with open(A.config_path(), "w", encoding="utf-8") as f:
    json.dump({"opacity": 999, "left": {"mana": 99, "sprites": ["不存在", keys[0]]}}, f)
A.load_config()
check("脏配置透明度被夹到100", A.STATE["opacity"] == 100)
check("脏配置魔力被夹到4", A.STATE["left"]["mana"] == 4)
check("脏精灵key被过滤", A.STATE["left"]["sprites"][0] is None
      and A.STATE["left"]["sprites"][1] == keys[0])

# 11. 精灵阵亡：数据、魔力联动、按钮同步、重置、持久化、渲染
check("new_side含fainted全False", A.new_side()["fainted"] == [False] * 6)
A.STATE["left"]["sprites"] = list(keys[:6])
A.STATE["left"]["fainted"] = [False] * 6; A.STATE["left"]["mana"] = 4
panel.toggle_faint("left", 0); panel.toggle_faint("left", 1)
check("标记两只阵亡", A.STATE["left"]["fainted"][:2] == [True, True]
      and A.STATE["left"]["fainted"][2:] == [False] * 4)
check("阵亡联动魔力4->2", A.STATE["left"]["mana"] == 2)
panel.toggle_faint("left", 0)
check("取消阵亡魔力回3", A.STATE["left"]["mana"] == 3
      and A.STATE["left"]["fainted"][0] is False)
A.STATE["right"]["sprites"] = [None] * 6; A.STATE["right"]["mana"] = 4
panel.toggle_faint("right", 3)
check("空槽标记阵亡无效", A.STATE["right"]["fainted"][3] is False
      and A.STATE["right"]["mana"] == 4)
fb = [b for b in panel.faint_buttons if b.side_key == "left" and b.idx == 1][0]
check("阵亡按钮勾选同步", fb.isChecked() is True and fb.isEnabled())
fp = A.fainted_pix(A.load_pix(A.SPRITE_BY_KEY[keys[0]]["avatar"]), 48)
check("阵亡头像有效且尺寸48", not fp.isNull() and fp.width() == 48
      and fp.height() == 48)
# 应用预设重置阵亡
A.QInputDialog.getText = staticmethod(lambda *a, **k: ("阵亡测试预设", True))
panel.save_preset("left"); panel.edits["left"]["preset"].setCurrentIndex(0)
panel.apply_preset("left")
check("应用预设清空阵亡", A.STATE["left"]["fainted"] == [False] * 6)
# 配置往返保留阵亡
A.STATE["left"]["fainted"][0] = True
A.save_config(); A.STATE["left"]["fainted"] = [False] * 6
A.load_config()
check("配置往返阵亡恢复", A.STATE["left"]["fainted"][0] is True)
with open(A.config_path(), "w", encoding="utf-8") as f:
    json.dump({"left": {"sprites": list(keys[:6])}}, f)
A.load_config()
check("旧配置fainted补全False", A.STATE["left"]["fainted"] == [False] * 6)

# 12. 外部文件：模板 / 导入解析 / 容错 / 导出往返 / 上限
tpl = os.path.join(tmp, "tpl.xlsx")
A.write_template_file(tpl)
check("模板文件生成", os.path.exists(tpl))
trows = A.read_preset_rows(tpl)
check("模板含表头+2示例", len(trows) == 3 and trows[0] == A.PRESET_COLUMNS)
trecs, terrs = A.build_preset_records(trows)
check("模板示例全部解析成功", len(trecs) == 2 and not terrs
      and all(all(x is not None for x in r["sprites"]) for r in trecs))
k0, k1, k2 = keys[0], keys[1], keys[2]
imp_txt = os.path.join(tmp, "in.txt")
open(imp_txt, "w", encoding="utf-8").write("\n".join([
    ",".join(A.PRESET_COLUMNS),
    ",".join(["队伍X", "选手乙", k0, k1, k2, "", "", ""]),
    ",".join(["队伍Y", "", "不存在的精灵", k0, "", "", "", ""]),
]))
recs, errs = A.build_preset_records(A.read_preset_rows(imp_txt))
check("txt导入2条记录", len(recs) == 2)
check("队伍X精灵解析", recs[0]["sprites"][:3] == [k0, k1, k2])
check("选手名记录", recs[0]["player"] == "选手乙")
check("坏精灵报错", any("队伍Y" in e for e in errs))
# 无表头按固定位置解析
imp2 = os.path.join(tmp, "in2.csv")
open(imp2, "w", encoding="utf-8").write("\n".join([
    ",".join(["无表头队", "选手丙", k0, k1, "", "", "", ""]),
]))
r2, e2 = A.build_preset_records(A.read_preset_rows(imp2))
check("无表头按位置解析", len(r2) == 1 and r2[0]["sprites"][:2] == [k0, k1])
# 唯一名称匹配
us = next(s for s in A.SPRITES if len(A._BY_NAME[s["name"]]) == 1)
check("唯一名称可解析", A.resolve_sprite(us["name"])[0] == us["key"])
# 导出往返
A.STATE["presets"] = [{"name": "P1", "sprites": [k0, k1] + [None] * 4}]
out_xlsx = os.path.join(tmp, "out.xlsx")
A.export_preset_file(out_xlsx, A.STATE["presets"])
back, berr = A.build_preset_records(A.read_preset_rows(out_xlsx))
check("导出往返内容一致", len(back) == 1 and back[0]["sprites"][:2] == [k0, k1])
check("MAX_PRESET提高到500", A.MAX_PRESET == 500)

print("\n==== 结果: %d 通过, %d 失败 ====" % (len(PASS), len(FAIL)))
sys.exit(1 if FAIL else 0)
