#!/bin/bash
# encoding: utf-8
#
# 用真 rime_deployer 驗證 dist/ 入面每個 iOS 方案包：
#   1. 整包部署（rime_deployer --build）冇致命錯誤
#   2. 逐個方案單獨編譯（--compile），而且係喺「空 shared dir」之下做 —— 模擬 iOS
#      元書冇自帶任何方案嘅最壞情況，確保 lite 版唔會因為缺依賴而爆
#   3. default.yaml 列出嘅每個方案都真係編譯出 .bin
#
# 註：entry_collector.cc 嘅 "Encode failure: '某某詞'" 係本碼表（enable_encoder）本身
#     已知噪音，桌面版一樣有，唔算打包問題。
#
# 用法：bash scripts/verify_ios_package.sh [dist 目錄] [包名前綴]
set -u

DIST="${1:-dist}"
PREFIX="${2:-rime-cangJie5_advanced}"
BENIGN='Encode failure'
FATAL=0

command -v rime_deployer >/dev/null || {
  echo "搵唔到 rime_deployer（Ubuntu: apt-get install -y ibus-rime）"
  exit 2
}

EMPTY_SHARED="$(mktemp -d)"
trap 'rm -rf "$EMPTY_SHARED"' EXIT

fail() { echo "  !! $1"; FATAL=1; }

check_log() {
  local log="$1" label="$2" real real_e real_w benign
  benign=$(grep -c "$BENIGN" "$log" 2>/dev/null || true)
  real=$(grep -v "$BENIGN" "$log" 2>/dev/null || true)
  real_e=$(printf '%s\n' "$real" | grep -c '^E' || true)
  real_w=$(printf '%s\n' "$real" | grep -c '^W' || true)
  echo "  ${label}：已知噪音 ${benign} 行 ／ 其他錯誤 ${real_e} ／ 其他警告 ${real_w}"
  if [ "$real_e" != "0" ]; then
    printf '%s\n' "$real" | grep '^E' | head -10
    fail "${label} 有錯誤"
  fi
  if [ "$real_w" != "0" ]; then
    printf '%s\n' "$real" | grep '^W' | head -10
  fi
  if printf '%s\n' "$real" | grep -qiE 'cannot find|not found|no such file|failed to load'; then
    printf '%s\n' "$real" | grep -iE 'cannot find|not found|no such file|failed to load' | head -10
    fail "${label} 有檔案搵唔到"
  fi
}

shopt -s nullglob
pkgs=("$DIST"/"$PREFIX"-*/)
if [ ${#pkgs[@]} -eq 0 ]; then
  echo "dist 入面搵唔到包：$DIST/$PREFIX-*/"
  exit 2
fi

for pkg in "${pkgs[@]}"; do
  name="$(basename "$pkg")"
  work="/tmp/verify-$name"
  echo "########## $name ##########"
  rm -rf "$work"
  cp -r "$pkg" "$work"

  # --- 1) 整包部署 ---
  rime_deployer --build "$work" >"/tmp/$name.build.log" 2>&1
  echo "  --build exit=$?"
  check_log "/tmp/$name.build.log" "--build"

  # --- 2) 逐個方案單獨編譯（空 shared dir ＝ 模擬 iOS 冇自帶方案）---
  schemas="$(awk '/^schema_list:/{f=1;next} f&&/^[^ ]/{f=0} f&&/^  - schema:/{gsub(/^  - schema: */,"");print}' "$work/default.yaml" | tr -d '\r')"
  if [ -z "$schemas" ]; then
    fail "default.yaml 冇 schema_list"
  fi
  for sid in $schemas; do
    if [ ! -f "$work/$sid.schema.yaml" ]; then
      fail "$sid 喺 schema_list 但冇 $sid.schema.yaml"
      continue
    fi
    rime_deployer --compile "$work/$sid.schema.yaml" "$work" "$EMPTY_SHARED" \
      >"/tmp/$name.$sid.log" 2>&1
    rc=$?
    if [ "$rc" != "0" ]; then
      fail "$sid --compile exit=$rc"
    fi
    check_log "/tmp/$name.$sid.log" "compile $sid"
  done

  # --- 3) build/ 產出檢查（方案碼表可能改名，所以用前綴比對）---
  for sid in $schemas; do
    if compgen -G "$work/build/$sid*.bin" >/dev/null; then
      size=$(du -ch "$work"/build/"$sid"*.bin 2>/dev/null | tail -1 | cut -f1)
      echo "  [ OK ] $sid 已編譯（$size）"
    else
      fail "$sid 冇編譯出 build/$sid*.bin"
    fi
  done
  echo
done

if [ "$FATAL" != "0" ]; then
  echo "驗證失敗：唔應該發佈"
  exit 1
fi
echo "驗證通過：所有包都可以喺（連空 shared dir 嘅）環境正常部署"
