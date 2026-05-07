"""
test_app_control.py — 测试 Windows 应用控件感知能力
在本地 Windows 运行，先手动打开微信，然后跑这个脚本。
"""
import sys
import json

print("=" * 50)
print("  YI-Agent-V3 — app_control 测试脚本")
print("=" * 50)

# 测试 1：列出所有可见窗口
print("\n=== 测试 1：所有可见窗口 ===")
try:
    import pygetwindow as gw
    windows = [w for w in gw.getAllWindows() if w.visible and w.title.strip()]
    for w in windows[:20]:
        flag = " [激活]" if w.isActive else ""
        print(f"  {w.title}{flag}")
    print(f"  共 {len(windows)} 个可见窗口")
except Exception as e:
    print(f"  ❌ pygetwindow 失败: {e}")

# 测试 2：找微信窗口
print("\n=== 测试 2：查找微信窗口 ===")
try:
    matches = [w for w in gw.getWindowsWithTitle("微信") if w.visible]
    if matches:
        w = matches[0]
        w.activate()
        print(f"  ✅ 找到: {w.title}")
        print(f"     位置: ({w.left}, {w.top})")
        print(f"     大小: {w.width}x{w.height}")
    else:
        print("  ⚠️ 未找到微信窗口，请确认微信已打开")
except Exception as e:
    print(f"  ❌ 查找失败: {e}")

# 测试 3：用 pywinauto 枚举控件
print("\n=== 测试 3：pywinauto 控件树 ===")
try:
    from pywinauto import Desktop

    # 先尝试找微信
    dlg = Desktop(backend="uia").window(title_re=".*微信.*")
    if dlg.exists():
        print(f"  ✅ 找到微信窗口，枚举控件...")

        # 列出前 30 个控件
        print("\n  --- 前 30 个控件 ---")
        for i, ctrl in enumerate(dlg.descendants()[:30]):
            ctype = ctrl.element_info.control_type
            text = ctrl.window_text()[:60] if ctrl.window_text() else ""
            name = ctrl.element_info.name or ""
            print(f"  [{i:2d}] {ctype:12s} | text='{text}' | name='{name}'")

        # 专门找 Edit 控件（输入框）
        print("\n  --- 所有 Edit 控件（输入框）---")
        edits = [c for c in dlg.descendants() if c.element_info.control_type == "Edit"]
        if edits:
            for edit in edits:
                rect = edit.rectangle()
                print(f"  ✅ Edit: '{edit.window_text()[:50]}'")
                print(f"     位置: ({rect.left},{rect.top}) 大小: {rect.width()}x{rect.height()}")
        else:
            print("  ⚠️ 未找到 Edit 控件")

        # 专门找 Button 控件
        print("\n  --- 所有 Button 控件 ---")
        buttons = [c for c in dlg.descendants() if c.element_info.control_type == "Button"]
        if buttons:
            for btn in buttons[:15]:
                print(f"  🔘 Button: '{btn.window_text()[:50]}'")
        else:
            print("  ⚠️ 未找到 Button 控件")

        # 找搜索相关控件
        print("\n  --- 搜索相关控件 ---")
        search_keywords = ["搜索", "search", "查找", "输入"]
        found_search = False
        for ctrl in dlg.descendants():
            text = (ctrl.window_text() or "").lower()
            name = (ctrl.element_info.name or "").lower()
            if any(kw in text or kw in name for kw in search_keywords):
                rect = ctrl.rectangle()
                print(f"  🔍 {ctrl.element_info.control_type}: '{ctrl.window_text()[:50]}'")
                print(f"     name='{ctrl.element_info.name}'")
                print(f"     位置: ({rect.left},{rect.top}) 大小: {rect.width()}x{rect.height()}")
                found_search = True
        if not found_search:
            print("  ⚠️ 未找到搜索相关控件")

    else:
        print("  ⚠️ pywinauto 未找到微信窗口")
        # 列出所有可用窗口
        print("\n  --- pywinauto 可见窗口 ---")
        for w in Desktop(backend="uia").windows():
            if w.is_visible():
                print(f"  📱 {w.window_text()}")

except Exception as e:
    print(f"  ❌ pywinauto 失败: {e}")
    import traceback
    traceback.print_exc()

# 测试 4：检查 pywinauto 是否可用
print("\n=== 测试 4：环境检查 ===")
try:
    import pywinauto
    print(f"  ✅ pywinauto 版本: {pywinauto.__version__}")
except Exception as e:
    print(f"  ❌ pywinauto: {e}")

try:
    import pygetwindow
    print(f"  ✅ pygetwindow 可用")
except Exception as e:
    print(f"  ❌ pygetwindow: {e}")

print("\n" + "=" * 50)
print("  测试完成！把以上全部输出复制给我。")
print("=" * 50)
