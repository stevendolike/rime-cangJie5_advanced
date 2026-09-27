#!/usr/bin/env python3
# encoding: utf-8
"""
Build 元書輸入法 (iOS / Hamster 3) installable Rime packages for this repo.

輸出兩個 zip：
  lite  = 本 repo 自帶方案（倉頡 / 進階速成 / 倉35粵混候 / 粵拼）+ opencc
  full  = lite + 反查依賴（luna_pinyin / stroke / loengfan）+ quick5 + emoji

用法：
  python3 scripts/build_ios_package.py --root . --deps third_party --out dist
  python3 scripts/build_ios_package.py --root . --deps third_party --out dist --variant lite

設計重點（給將來維護嘅人）：
  * 打包內容 = zip 內單一頂層資料夾，內裏就係 Rime 用戶目錄（user dir）嘅內容。
    元書「壓縮包導入」／「下載方案」解壓後，嗰個頂層資料夾就會成為「方案目錄」，
    用家喺元書「輸入方案 → 方案目錄切換」揀返佢即可。
  * default.yaml 嘅 schema_list 會自動重寫成「實際存在嘅方案」，避免列出唔存在嘅方案。
  * 驗證分兩級：error（一定要有，缺咗就 build 失敗）／warning（可能由 App 自帶提供，只提示）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

try:
    import yaml
except ImportError:  # PyYAML 只係用嚟驗證
    yaml = None

# --------------------------------------------------------------------------- #
# 設定
# --------------------------------------------------------------------------- #

REPO_FILE_GLOBS = ("*.yaml", "*.txt", "opencc/*")

# 方案顯示優先次序（default.yaml 內 schema_list 會照此排序，只列出實際存在嘅）
SCHEMA_ORDER = [
    "cangjie5_advanced",
    "cangjie5",
    "ms_quick",
    "quick5",
    "cangjie5_express",
    "jyut6ping3",
    "jyut6ping3_ipa",
    "luna_pinyin",
    "loengfan",
    "stroke",
]

# 呢啲方案只係做反查依賴／內部變體，唔需要出現喺方案選單
SCHEMA_LIST_EXCLUDE = {
    "luna_quanpin",
    "luna_pinyin_fluency",
    "luna_pinyin_simp",
    "luna_pinyin_tw",
}

TEXT_SUFFIXES = (".yaml", ".txt", ".json")

# 依賴來源（CI 會 clone 到 --deps 之下，資料夾名 = repo 名）
# 每個 repo 只取指定檔案，repo 自身檔案最後 overlay 上去（repo 優先）。
DEP_RULES: dict[str, list[str]] = {
    "rime-cantonese": ["opencc/t2hkf.json", "opencc/HKVariantsFull.txt"],
    "rime-quick": ["quick5.schema.yaml", "quick5.dict.yaml", "quick5.supplement.dict.yaml"],
    "rime-cangjie": ["cangjie5.base.dict.yaml"],
    "rime-stroke": ["stroke.schema.yaml", "stroke.dict.yaml"],
    "rime-luna-pinyin": [
        "luna_pinyin.schema.yaml",
        "luna_pinyin.dict.yaml",
        "luna_quanpin.schema.yaml",
        "luna_pinyin_fluency.schema.yaml",
        "luna_pinyin_simp.schema.yaml",
        "luna_pinyin_tw.schema.yaml",
        "pinyin.yaml",
    ],
    "rime-loengfan": ["loengfan.schema.yaml", "loengfan.dict.yaml"],
    "rime-emoji-cantonese": ["opencc/emoji_cantonese.json", "opencc/emoji_cantonese.txt"],
}

# 依賴檔名（用嚟做「缺咗都算 error」嘅判斷）
FULL_ONLY_DEP_SCHEMAS = {"quick5", "stroke", "luna_pinyin", "loengfan", "luna_quanpin"}

REQUIRED_REPO_FILES = [
    "default.yaml",
    "symbols_cantonese.yaml",
    "symbols.yaml",
    "punctuation.yaml",
    "key_bindings.yaml",
]

OPTIONAL_INCLUDE_RE = re.compile(r"\?\s*$")


def log(msg: str) -> None:
    print(msg, flush=True)


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)
        log(f"  [ERROR] {msg}")

    def warn(self, msg: str) -> None:
        if msg not in self.warnings:
            self.warnings.append(msg)
            log(f"  [WARN ] {msg}")

    def ok(self, msg: str) -> None:
        log(f"  [ OK  ] {msg}")


# --------------------------------------------------------------------------- #
# 收集檔案
# --------------------------------------------------------------------------- #

def collect_repo_files(root: Path) -> list[str]:
    files: list[str] = []
    for pattern in REPO_FILE_GLOBS:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                files.append(path.relative_to(root).as_posix())
    # 排除唔應該入 iOS 包嘅 root 檔案
    drop = {"install.sh"}
    return [f for f in files if f not in drop]


def collect_dep_files(deps: Path, rules: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    """回傳 (檔案清單(相對 deps), 缺少嘅檔案清單)"""
    found: list[str] = []
    missing: list[str] = []
    for repo, wanted in rules.items():
        repo_dir = deps / repo
        if not repo_dir.is_dir():
            for item in wanted:
                missing.append(f"{repo}/{item}")
            continue
        for item in wanted:
            if (repo_dir / item).is_file():
                found.append(f"{repo}/{item}")
            else:
                missing.append(f"{repo}/{item}")
    return found, missing


# --------------------------------------------------------------------------- #
# default.yaml: 重寫 schema_list
# --------------------------------------------------------------------------- #

def rewrite_schema_list(text: str, schemas: list[str]) -> str:
    lines = text.splitlines(keepends=False)
    out: list[str] = []
    i = 0
    replaced = False
    while i < len(lines):
        line = lines[i]
        if re.match(r"^schema_list\s*:", line):
            indent = "  "
            out.append(line)
            for schema in schemas:
                out.append(f"{indent}- schema: {schema}")
            i += 1
            # 吃掉舊嘅 list 項（同層縮排嘅 - schema: ... / 註釋 / 空行）
            while i < len(lines) and (
                re.match(r"^\s*-\s*schema\s*:", lines[i])
                or re.match(r"^\s*#", lines[i])
                or lines[i].strip() == ""
            ):
                if lines[i].strip() == "" and i + 1 < len(lines) and not re.match(
                    r"^\s*(-\s*schema\s*:|#)", lines[i + 1]
                ):
                    break
                i += 1
            replaced = True
            continue
        out.append(line)
        i += 1
    if not replaced:
        out.append("")
        out.append("schema_list:")
        for schema in schemas:
            out.append(f"  - schema: {schema}")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- #
# 驗證
# --------------------------------------------------------------------------- #

def dict_header(text: str) -> str:
    """Rime 字典檔喺 `...` 之後係 tab 分隔嘅詞條，唔屬 YAML，所以只取 header。"""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "...":
            return "\n".join(lines[:i])
    return text


def load_yaml_file(path: Path, report: Report, strict: bool = True) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        report.error(f"{path.name}: 唔係合法 UTF-8（{exc}）")
        return None
    if yaml is None:
        return {}
    if path.name.endswith(".dict.yaml"):
        text = dict_header(text)
    try:
        data = yaml.safe_load(text)
    except Exception as exc:  # noqa: BLE001
        msg = f"{path.name}: YAML 解析失敗（{exc}）"
        report.error(msg) if strict else report.warn(msg)
        return None
    return data if isinstance(data, dict) else {}


def validate(root_dir: Path, files: dict[str, Path], variant: str, report: Report) -> None:
    names = {Path(f).name for f in files}
    rels = set(files)

    # 1) UTF-8 檢查（所有檔案）
    for rel, path in files.items():
        if not rel.endswith(TEXT_SUFFIXES):
            continue  # .ocd2 等二進位檔唔需要係 UTF-8
        try:
            path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            report.error(f"{rel}: 唔係合法 UTF-8（元書要求 UTF-8）")

    # 2) 必要檔案
    for req in REQUIRED_REPO_FILES:
        if req not in names:
            report.error(f"缺少必要檔案：{req}")

    # 3) 逐個 schema 檢查
    schema_ids: dict[str, str] = {}
    deps_needed: set[str] = set()
    for rel, path in files.items():
        if not rel.endswith(".schema.yaml"):
            continue
        data = load_yaml_file(path, report)
        if data is None:
            continue
        schema = data.get("schema") or {}
        sid = schema.get("schema_id")
        if not sid:
            report.error(f"{rel}: 缺少 schema/schema_id")
            continue
        if sid in schema_ids:
            report.error(f"schema_id 重複：{sid}（{rel} 同 {schema_ids[sid]}）")
        schema_ids[sid] = rel
        expected_name = Path(rel).name[: -len(".schema.yaml")]
        if sid != expected_name:
            report.warn(f"{rel}: schema_id（{sid}）同檔名唔一致，載入時要對得上")
        for dep in schema.get("dependencies") or []:
            deps_needed.add(str(dep))

    # 4) dependencies
    for dep in sorted(deps_needed):
        if dep in schema_ids:
            continue
        if dep in FULL_ONLY_DEP_SCHEMAS:
            if variant == "full":
                report.error(f"dependencies 缺少方案 {dep}.schema.yaml（full 版應該有）")
            else:
                report.warn(
                    f"dependencies 缺少方案 {dep}：元書嘅 RimeSharedSupport 唔包含 PC 內置方案"
                    f"（官方文檔），所以 lite 版冇得靠 App，反查會冇料；要反查請用 full 版"
                )
        else:
            report.warn(f"dependencies 缺少方案 {dep}（可能由前端 App 自帶提供）")

    # 5) 字典 import_tables / vocabulary
    for rel, path in files.items():
        if not rel.endswith(".dict.yaml"):
            continue
        data = load_yaml_file(path, report) or {}
        for table in data.get("import_tables") or []:
            table = str(table)
            if Path(table).suffix:
                candidate = f"{table}.dict.yaml"
            else:
                candidate = f"{table}.dict.yaml"
            if candidate not in names:
                report.error(f"{rel}: import_tables 指住唔存在嘅字典 {candidate}")
        vocab = data.get("vocabulary")
        if vocab:
            if f"{vocab}.txt" not in names:
                report.warn(f"{rel}: vocabulary 檔 {vocab}.txt 唔喺包入面（影響詞頻，唔影響打字）")
        if data.get("use_preset_vocabulary") and "essay.txt" not in names:
            report.warn(
                f"{rel}: use_preset_vocabulary 需要 essay.txt，但唔喺包入面（只影響詞頻排序）"
            )

    # 6) opencc_config / import_preset / __include
    for rel, path in files.items():
        if not (rel.endswith(".yaml")):
            continue
        if rel.endswith(".dict.yaml"):
            continue
        data = load_yaml_file(path, report) or {}
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                for key, value in node.items():
                    stack.append(value)
                    if key == "opencc_config" and isinstance(value, str):
                        if f"opencc/{value}" not in rels:
                            report.warn(
                                f"{rel}: opencc_config {value} 唔喺包入面（靠 App 自帶 opencc；"
                                f"標準 opencc config 一般都有，得 t2hkf/emoji 要自己帶）"
                            )
                    if key == "import_preset" and isinstance(value, str):
                        if f"{value}.yaml" not in names and value != "default":
                            report.warn(f"{rel}: import_preset {value} 唔喺包入面")
                    if key in ("__include", "__patch", "__merge") and isinstance(value, str):
                        target = value
                        optional = bool(OPTIONAL_INCLUDE_RE.search(target))
                        target = target.rstrip("?").strip()
                        base = target.split(":", 1)[0]
                        if base and f"{base}.yaml" not in names:
                            msg = f"{rel}: {key} 指住 {value}，但 {base}.yaml 唔喺包入面"
                            report.warn(msg) if optional else report.error(msg)
            elif isinstance(node, list):
                stack.extend(node)

    report.ok(f"掃描到 {len(schema_ids)} 個方案：{', '.join(sorted(schema_ids))}")


# --------------------------------------------------------------------------- #
# 打包
# --------------------------------------------------------------------------- #

def build_variant(
    root: Path,
    deps: Path,
    out: Path,
    variant: str,
    name: str,
    report: Report,
) -> dict:
    log(f"\n=== 打包 {variant} 版：{name} ===")
    staging = out / name
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    repo_files = collect_repo_files(root)
    files: dict[str, Path] = {rel: root / rel for rel in repo_files}

    if variant == "full":
        dep_files, dep_missing = collect_dep_files(deps, DEP_RULES)
        # 先放依賴，再由 repo 覆蓋（repo 優先）
        for rel in dep_files:
            repo, _, inner = rel.partition("/")
            files.setdefault(inner, deps / repo / inner)
        for rel in dep_files:
            _, _, inner = rel.partition("/")
            files[inner] = deps / rel
        repo_overlay = {rel: root / rel for rel in repo_files}
        files.update(repo_overlay)  # repo 檔案最終覆蓋
        for miss in dep_missing:
            report.error(f"缺少依賴檔案：{miss}（third_party 未 clone 齊？）")
    else:
        # lite 版都要補回 opencc/t2hkf.json（香港傳統漢字用），呢個係上游 rime-cantonese 檔案
        extra = DEP_RULES["rime-cantonese"]
        for item in extra:
            src = deps / "rime-cantonese" / item
            if src.is_file():
                files[item] = src
            else:
                report.warn(f"lite 版未能補回 {item}（香港傳統漢字選項可能失效）")

    # 抄檔入 staging
    for rel, src in sorted(files.items()):
        dest = staging / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)

    # 重寫 default.yaml schema_list
    present_schemas = [
        sid
        for sid in SCHEMA_ORDER
        if (staging / f"{sid}.schema.yaml").is_file()
    ]
    known = {
        Path(f).name[: -len(".schema.yaml")]
        for f in files
        if f.endswith(".schema.yaml")
    }
    for extra_id in sorted(known - set(present_schemas) - SCHEMA_LIST_EXCLUDE):
        present_schemas.append(extra_id)
    default_yaml = staging / "default.yaml"
    if default_yaml.is_file():
        text = default_yaml.read_text(encoding="utf-8")
        default_yaml.write_text(rewrite_schema_list(text, present_schemas), encoding="utf-8")
        report.ok(f"default.yaml schema_list → {', '.join(present_schemas)}")

    # 資訊檔（<文件名>-info.txt 會畀元書複製入 user dir，只係純文字，冇副作用）
    info = {
        "package": name,
        "variant": variant,
        "generated_for": "iOS 元書輸入法 (Hamster 3)",
        "schemas": present_schemas,
        "file_count": len(files),
        "note": "Rime 用戶目錄內容；喺元書用「壓縮包導入」或「下載方案」導入後，"
                "去「輸入方案 → 方案目錄切換」揀返呢個資料夾。",
    }
    (staging / "package-info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # 驗證
    staged = {
        p.relative_to(staging).as_posix(): p
        for p in staging.rglob("*")
        if p.is_file()
    }
    validate(staging, staged, variant, report)

    # 打包 zip（固定時間戳 = 可重現 build）
    zip_path = out / f"{name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel in sorted(staged):
            info_zip = zipfile.ZipInfo(f"{name}/{rel}", date_time=(1980, 1, 1, 0, 0, 0))
            info_zip.compress_type = zipfile.ZIP_DEFLATED
            info_zip.external_attr = 0o644 << 16
            zf.writestr(info_zip, staged[rel].read_bytes())

    size = zip_path.stat().st_size
    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    report.ok(f"{zip_path.name}: {size/1048576:.2f} MiB, {len(staged)} 個檔案, sha256={sha[:16]}…")
    return {
        "name": name,
        "variant": variant,
        "zip": zip_path.name,
        "bytes": size,
        "sha256": sha,
        "files": len(staged),
        "schemas": present_schemas,
        "errors": list(report.errors),
        "warnings": list(report.warnings),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="repo 根目錄")
    ap.add_argument("--deps", default="third_party", help="已 clone 嘅依賴 repo 目錄")
    ap.add_argument("--out", default="dist", help="輸出目錄")
    ap.add_argument("--variant", default="both", choices=["lite", "full", "both"])
    ap.add_argument("--name-prefix", default="rime-cangJie5_advanced")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    deps = Path(args.deps).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    variants = ["lite", "full"] if args.variant == "both" else [args.variant]
    report = Report()
    results = []
    for variant in variants:
        name = f"{args.name_prefix}-{variant}"
        results.append(build_variant(root, deps, out, variant, name, report))

    summary = {
        "generated_at": os.environ.get("BUILD_TIME", ""),
        "commit": os.environ.get("GITHUB_SHA", ""),
        "packages": results,
        "errors": report.errors,
        "warnings": report.warnings,
    }
    (out / "ios-packages.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    log("\n================ 總結 ================")
    for res in results:
        log(f"  {res['zip']}: {res['bytes']/1048576:.2f} MiB, {res['files']} 檔")
    log(f"  error={len(report.errors)} warning={len(report.warnings)}")
    if report.errors:
        log("\n有 error，唔應該發佈：")
        for err in report.errors:
            log(f"  - {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
