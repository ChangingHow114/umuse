#!/bin/bash
# ============================================================
# UMuse .app 构建脚本 / Build .app bundle for macOS
# ============================================================
# 用法: bash scripts/build_app.sh
# 输出: dist/UMuse.app (可拖入 /Applications 或 Dock)
# ============================================================

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$PROJECT_DIR/dist/UMuse.app"
PYTHON="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"

echo "=== 构建 UMuse.app ==="

# 1. 清理并创建目录结构
echo "[1/4] 创建目录结构..."
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# 2. 写入启动脚本
echo "[2/4] 写入启动脚本..."
cat > "$APP_DIR/Contents/MacOS/UMuse" << 'LAUNCHER'
#!/bin/bash
PROJECT_DIR="LAUNCHER_PLACEHOLDER"
PYTHON="PYTHON_PLACEHOLDER"
LOG_FILE="$HOME/.umuse_launch.log"
echo "=== UMuse $(date) ===" >> "$LOG_FILE"
export PATH="$PATH:/opt/homebrew/bin"
cd "$PROJECT_DIR" || {
    osascript -e 'display dialog "无法找到 UMuse 项目目录。" with title "UMuse 启动失败" with icon stop buttons {"确定"}'
    exit 1
}
arch -arm64 "$PYTHON" main.py gui >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
# 0=正常 130=SIGINT 143=SIGTERM 134=SIGABRT(Qt线程清理) 139=SIGSEGV
if [ $EXIT_CODE -eq 0 ] || [ $EXIT_CODE -eq 130 ] || [ $EXIT_CODE -eq 143 ] || [ $EXIT_CODE -eq 134 ] || [ $EXIT_CODE -eq 139 ]; then
    echo "Exit: $EXIT_CODE (ok)" >> "$LOG_FILE"
else
    echo "Exit: $EXIT_CODE (error)" >> "$LOG_FILE"
    osascript -e 'display dialog "UMuse 启动失败 (错误码: '$EXIT_CODE')\n\n请查看日志:\n~/.umuse_launch.log" with title "UMuse" with icon stop buttons {"确定"}'
fi
LAUNCHER

# 替换占位符
sed -i '' "s|LAUNCHER_PLACEHOLDER|$PROJECT_DIR|g" "$APP_DIR/Contents/MacOS/UMuse"
sed -i '' "s|PYTHON_PLACEHOLDER|$PYTHON|g" "$APP_DIR/Contents/MacOS/UMuse"
chmod +x "$APP_DIR/Contents/MacOS/UMuse"

# 3. 写入 Info.plist
echo "[3/4] 写入 Info.plist..."
cat > "$APP_DIR/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleName</key>
	<string>UMuse</string>
	<key>CFBundleDisplayName</key>
	<string>UMuse</string>
	<key>CFBundleIdentifier</key>
	<string>com.umuse.app</string>
	<key>CFBundleVersion</key>
	<string>0.1.0</string>
	<key>CFBundleShortVersionString</key>
	<string>0.1.0</string>
	<key>CFBundleExecutable</key>
	<string>UMuse</string>
	<key>CFBundleIconFile</key>
	<string>UMuse</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>LSMinimumSystemVersion</key>
	<string>14.0</string>
	<key>NSHighResolutionCapable</key>
	<true/>
</dict>
</plist>
PLIST

# 4. 生成图标
echo "[4/4] 生成应用图标..."
"$PYTHON" << 'PYEOF'
from PIL import Image, ImageDraw
import os

SIZE = 1024
img = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# 圆角方形背景
draw.rounded_rectangle([80, 80, SIZE-80, SIZE-80], radius=180, fill=(58, 35, 95, 255))
# 内圈
draw.ellipse([200, 200, SIZE-200, SIZE-200], fill=(130, 80, 200, 255))
# 音符图标 (白色)
cx, cy = SIZE//2, SIZE//2
white = (255, 255, 255, 255)
line_x = cx + 40
draw.rectangle([line_x-16, cy-200, line_x+16, cy+80], fill=white)
draw.ellipse([cx-180, cy+40, cx+40, cy+160], fill=white)
draw.arc([line_x-20, cy-200, line_x+200, cy-20], start=0, end=180, fill=white, width=24)

# 生成各尺寸
iconset = '/tmp/UMuse.iconset'
if os.path.exists(iconset):
    import shutil; shutil.rmtree(iconset)
os.makedirs(iconset)
for s in [16, 32, 64, 128, 256, 512]:
    img.resize((s, s), Image.LANCZOS).save(f'{iconset}/icon_{s}x{s}.png')
    s2 = s*2
    if s2 <= SIZE:
        img.resize((s2, s2), Image.LANCZOS).save(f'{iconset}/icon_{s}x{s}@2x.png')
img.save(f'{iconset}/icon_512x512@2x.png')
print(f'  {len(os.listdir(iconset))} icon sizes generated')
PYEOF

iconutil -c icns /tmp/UMuse.iconset -o "$APP_DIR/Contents/Resources/UMuse.icns"
touch "$APP_DIR"

echo ""
echo "=== 完成! ==="
echo "应用位置: $APP_DIR"
echo ""
echo "使用方式:"
echo "  1. 双击 dist/UMuse.app 启动"
echo "  2. 拖到 /Applications 目录"
echo "  3. 右键 Dock 图标 → 在 Dock 中保留"
echo "  4. 或者运行: open dist/UMuse.app"
