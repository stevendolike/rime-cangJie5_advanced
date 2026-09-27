[English](README-en.md) | [官話](README-cmn.md) | [首頁](README.md)

<div lang="yue-HK">

# iOS「元書輸入法」方案包

用緊 iPhone / iPad 都可以打倉頡＋粵拼？呢個 repo 每次方案檔案有改動，都會由 GitHub Actions 自動砌好可以直接畀 **元書輸入法**（Hamster 3，iOS 16+）導入嘅方案包，掛喺固定網址：

| 版本 | 內容 | 檔案 | 下載網址 |
| --- | --- | --- | --- |
| **lite（精簡）** | 本 repo 全部方案：倉35粵混候、倉頡五代、傳統速成、進階速成、粵拼、粵拼 IPA | 約 17 MB | `https://github.com/stevendolike/rime-cangJie5_advanced/releases/download/ios/rime-cangJie5_advanced-lite.zip` |
| **full（全套）** | lite 全部 ＋ 反查用嘅朙月拼音 / 筆畫 / 粵語兩分、速成 quick5、emoji 粵語建議 | 約 19 MB | `https://github.com/stevendolike/rime-cangJie5_advanced/releases/download/ios/rime-cangJie5_advanced-full.zip` |

兩個版本嘅 `default.yaml` 方案選單都已經自動整理好，只會列出真正有嘅方案。

> ⚠️ **建議用 full 版。** 元書官方文檔講明：「元書 RimeSharedSupport 目錄不包含 PC 上內置的輸入方案，
> 僅包含 default.yaml、opencc 等基礎配置；如果方案依賴 PC 內置輸入方案，請一齊打包。」
> 即係元書**冇自帶**朙月拼音／筆畫／粵語兩分，所以 lite 版嘅反查（`` ` ``／`r`／`x`）係冇料嘅，只有 full 版齊。
> lite 版適合只想打倉頡／速成／粵拼、唔要反查、想 zip 細啲嘅情況。

## 安裝步驟

### 先裝 App

- 元書輸入法（App Store 免費）：<https://apps.apple.com/hk/app/id6744464701>
- 裝完記得去 iOS「設定 → 一般 → 鍵盤 → 鍵盤 → 新增鍵盤 → 元書輸入法」，並開「允許完全取用」（部署要用）。

### 方法一：喺 App 內直接下載（最方便）

1. 打開元書 →「輸入方案」頁
2. 右上角選單 →「下載方案」
3. 撳右上角 ➕，貼上上面其中一條網址（檔名可以自己起，例如 `rime-cangJie5_advanced-lite`）
4. 喺清單撳綠色下載掣，等佢下載完
5. 返「輸入方案」頁 → 右上角選單 →「方案目錄切換」→ 揀返啱啱下載嗰個資料夾
6. 部署一次（App 會自己跑 RIME 部署），就可以喺鍵盤切換方案

### 方法二：壓縮包導入

1. 用電腦下載上面嘅 zip，或者用 Safari 直接下載（Safari 會問用邊個 App 開）
2. 揀「用元書輸入法打開」，App 會自動解壓導入
3. 之後同上面第 5、6 步一樣：「方案目錄切換」→ 揀資料夾 → 部署

### 方法三：WiFi 傳檔（電腦同手機同一個 Wi-Fi）

1. 元書 →「WiFi 文件傳輸」，記住顯示嘅網址
2. 電腦瀏覽器打開嗰個網址 → 入「RimeUserData」
3. 建議先建一個子資料夾（例如 `rime-cangJie5_advanced`），將 zip 解壓後嘅內容拖上去
4. 去「方案目錄切換」揀嗰個資料夾 → 部署

> 傳檔期間手機要長亮、唔可以切去後台，否則會斷。

## 用唔到／唔生效點算

| 症狀 | 處理 |
| --- | --- |
| 方案選單見唔到新方案 | 「方案目錄切換」揀錯資料夾；或者未重新部署。改完檔案要再部署一次先生效 |
| 改完檔案唔生效 | 元書會由 iCloud 存儲區／鍵盤存儲區複製檔案落應用存儲區，直接改應用存儲區嘅檔會被覆蓋。改檔請喺你揀嘅方案目錄（或 iCloud 存儲區）改 |
| 打唔到字、一片空白 | 去「輸入方案」重新部署；如果係皮膚問題，換返預設皮膚 |
| 反查（`／`r`／`x`）冇反應 | 用 lite 版時冇朙月拼音／筆畫／粵語兩分方案 → 改用 full 版 |
| 香港傳統漢字轉唔到 | 已包括 `opencc/t2hkf.json`；如果仍然唔得，係 App 內 opencc 冇載入，改用「傳統漢字」 |
| 想「臺灣傳統漢字」 | 靠 App 自帶 `opencc/t2tw.json`，本包冇附（App 一般都有） |

## Repo 關係

本 repo（`stevendolike/rime-cangJie5_advanced`）係 `Ramen-LadyHKG/rime-cangJie5_advanced` 嘅 fork，方案內容照上游同步；iOS 方案包嘅自動化 workflow 就喺呢邊跑（詳見下節）。

## 呢個包係點砌出嚟（自動化）

`.github/workflows/ios-package.yml`，觸發條件：

- `main` 分支有任何 `*.yaml` / `*.txt` / `opencc/**` 改動（包括每週四 upstream 同步之後）
- 每週六 10:00 UTC 定時重砌（跟到依賴方案嘅更新）
- 手動 `workflow_dispatch`（可以只砌 lite 或 full）

流程：

1. `git clone --depth 1` 拉依賴方案（rime-quick / rime-cangjie / rime-stroke / rime-luna-pinyin / CanCLID-rime-loengfan / rime-emoji-cantonese），並由上游 rime-cantonese 補 `opencc/t2hkf.json`
2. `scripts/build_ios_package.py` 砌包：收檔案 → 重寫 `default.yaml` 嘅 `schema_list` → 檢查 UTF-8、YAML、`import_tables`、`dependencies`、`opencc_config`、`__include` 有冇指向唔存在嘅檔 → 出 zip（zip 內係單一頂層資料夾，UTF-8，可重現 build）
3. `scripts/verify_ios_package.sh` 用真 `rime_deployer` 驗證：整包部署 + 逐個方案喺**空 shared dir**（模擬 iOS 冇自帶任何方案）之下單獨編譯，任何真錯誤／缺少檔案就唔發佈
4. 上傳 artifact，同時更新 Release（固定 tag `ios`）上面嘅 zip＋`SHA256SUMS.txt`＋`ios-packages.json`

想本地重跑：

```bash
# 需要 python3 + pyyaml；Ubuntu 另裝 ibus-rime 先有 rime_deployer
mkdir -p third_party && cd third_party
git clone --depth 1 https://github.com/rime/rime-quick.git
git clone --depth 1 https://github.com/rime/rime-cangjie.git
git clone --depth 1 https://github.com/rime/rime-stroke.git
git clone --depth 1 https://github.com/rime/rime-luna-pinyin.git
git clone --depth 1 https://github.com/CanCLID/rime-loengfan.git rime-loengfan
git clone --depth 1 https://github.com/rime/rime-emoji-cantonese.git
git clone --depth 1 --filter=blob:none --sparse https://github.com/rime/rime-cantonese.git
cd rime-cantonese && git sparse-checkout set opencc && cd ..
cd ..
python3 scripts/build_ios_package.py --root . --deps third_party --out dist --variant both
bash scripts/verify_ios_package.sh dist
```

要加減依賴（例如想連八股文語言模型 `grammar:/hant?` 都用得），改 `scripts/build_ios_package.py` 頂部嘅 `DEP_RULES` 即可。

## 已知限制

- 冇包含 `lotem/rime-octagram-data` 語言模型：`jyut6ping3` 嘅 `__patch: grammar:/hant?` 係可選項，冇都照打得，只係句子預測冇咁叻（iOS 上亦會慳好多空間）
- `enable_encoder` 產生嘅 `Encode failure` 訊息係碼表本身已知噪音（桌面版一樣有），唔影響出字
- 部署後 `build/` 大約佔 150 MB（lite）／220 MB（full），係 rime 編譯碼表嘅正常體積
- lite 版冇 `essay.txt`（詞頻統計用），只影響候選排序嘅細節

## 依賴方案來源（多謝）

- <https://github.com/rime/rime-cantonese>（`opencc/t2hkf.json`）
- <https://github.com/rime/rime-quick>、<https://github.com/rime/rime-cangjie>
- <https://github.com/rime/rime-stroke>、<https://github.com/rime/rime-luna-pinyin>
- <https://github.com/CanCLID/rime-loengfan>、<https://github.com/rime/rime-emoji-cantonese>

授權跟返各自 repo；本 repo 自帶部分見 [LICENSE-CC-BY](LICENSE-CC-BY)、[LICENSE-ODbL](LICENSE-ODbL)。

</div>
