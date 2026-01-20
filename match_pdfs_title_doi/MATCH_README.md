# 文献数据匹配工具使用指南

## 概述

本工具用于将 `pdfs` 文件夹中的 PDF 文件与 Scopus CSV 索引记录进行匹配，建立文献数据与 PDF 文件之间的关联。匹配成功后可用于后续的 MineRU PDF 转换处理。

## 目录结构

```
match_pdfs_title_doi/
├── match_records.py          # 主匹配脚本
├── scopus_csv_records/       # 存放 Scopus 导出的 CSV 文件
│   └── scopus_*.csv
├── match_results/            # 匹配结果输出目录
│   ├── matched/              # 成功匹配的记录（按期刊分）
│   ├── unmatched/            # 未匹配的记录（按期刊分）
│   ├── multi_matched/        # 多重匹配的记录（按期刊分）
│   ├── ALL_MATCHED.csv       # 所有匹配成功记录合并
│   ├── ALL_UNMATCHED.csv     # 所有未匹配记录合并（含下载链接）
│   └── ALL_MULTI_MATCHED.csv # 所有多重匹配记录合并
├── logs/                     # 日志文件
└── MATCH_README.md           # 本文档
```

## 匹配逻辑

### 1. PDF 文件名处理

不同期刊的 PDF 文件名格式不同：

| 期刊类型 | 文件名格式 | 示例 |
|---------|-----------|------|
| 有年份 | `{标题部分}_{年份}_{期刊名部分}.pdf` | `A-computer-vision-based_2024_Decision-Su.pdf` |
| 无年份 | `{标题}.pdf` | `Design Science Research.pdf` |
| DOI 格式 | `{DOI后缀}.pdf` | `isj.12026.pdf` |

脚本会根据期刊配置自动提取用于匹配的部分。

### 2. 文本标准化

匹配前，脚本会对 PDF 文件名和 CSV 内容进行标准化处理：
- 转换为纯小写字母
- 移除所有符号（包括空格、连字符、下划线等）
- Title 匹配时移除数字，DOI 匹配时保留数字

例如：
- 原始：`A-computer-vision-based-concept-model`
- 标准化：`acomputervisionbasedconceptmodel`

### 3. 匹配规则

**核心匹配逻辑**：CSV 记录的标准化内容必须**从头开始**包含 PDF 文件名的标准化内容。

```
CSV Title (标准化后): acomputervisionbasedconceptmodeltorecommenddomesticoverseaslike...
PDF 文件名 (标准化后): acomputervisionbasedconceptmodeltorecommenddomestic
                       ↑ 从头开始完全匹配 ✓
```

### 4. 期刊匹配模式

| 期刊 | 匹配列 | 文件名格式 | 特殊处理 |
|------|--------|-----------|---------|
| DSS, EJIS, IM, IO, JSIS, JIT | Title | 有年份 | - |
| JAIS, JMIS, MISQ | Title | 无年份 | - |
| ISJ | DOI | 无年份 | DOI 后缀匹配 |
| ISR | Title | 无年份 | 特殊编码移除 |

#### ISJ 期刊的 DOI 匹配

ISJ PDF 文件名为 DOI 后缀，如：
- `isj.12026.pdf` → DOI: `10.1111/isj.12026`
- `j.1365-2575.2006.00208.x.pdf` → DOI: `10.1111/j.1365-2575.2006.00208.x`

#### ISR 期刊的特殊处理

ISR PDF 文件名可能包含特殊编码：
- `#x3a;` → 冒号 `:`
- `#x3f;` → 问号 `?`
- `#x22;` → 引号 `"`

脚本会自动移除这些编码后再进行匹配。

### 5. 匹配结果分类

| 结果类型 | 说明 | 输出位置 |
|---------|------|---------|
| 成功匹配 | 找到唯一对应的 PDF | `matched/{期刊}_matched.csv` |
| 未匹配 | 未找到任何对应 PDF | `unmatched/{期刊}_unmatched.csv` |
| 多重匹配 | 找到多个对应 PDF | `multi_matched/{期刊}_multi_matched.csv` |

## 使用方法

### 基本用法

```powershell
# 激活虚拟环境
& .venv\Scripts\Activate.ps1

# 处理所有期刊（自动发现 pdfs/ 下的所有子目录）
uv run match_pdfs_title_doi/match_records.py

# 处理指定期刊
uv run match_pdfs_title_doi/match_records.py --journals DSS,EJIS,ISJ
```

### 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--input-dir` | `../pdfs` | PDF 文件目录（包含期刊子文件夹）|
| `--csv-dir` | `./scopus_csv_records` | CSV 文件目录 |
| `--output-dir` | `./match_results` | 输出目录 |
| `--log-dir` | `./logs` | 日志目录 |
| `--doi-journals` | `ISJ` | 使用 DOI 匹配的期刊（逗号分隔）|
| `--special-journals` | `ISR` | 需要特殊编码处理的期刊（逗号分隔）|
| `--journals` | (全部) | 要处理的期刊列表（逗号分隔）|
| `--csv-pattern` | `scopus_*.csv` | CSV 文件名匹配模式 |
| `--dry-run` | False | 仅检查，不保存结果 |

### 示例

```powershell
# 使用自定义路径
uv run match_pdfs_title_doi/match_records.py \
    --input-dir D:/my_pdfs \
    --csv-dir D:/csv_files \
    --output-dir D:/results

# 添加更多 DOI 匹配期刊
uv run match_pdfs_title_doi/match_records.py --doi-journals ISJ,CUSTOM_JOURNAL

# 添加更多特殊处理期刊
uv run match_pdfs_title_doi/match_records.py --special-journals ISR,ANOTHER_JOURNAL
```

## 输出文件

### 单期刊结果文件

#### matched CSV
原 CSV 列 + `Matched_PDF_Path`（匹配到的 PDF 完整路径）

#### unmatched CSV
原 CSV 列 + `Unmatch_Reason`（未匹配原因说明）

#### multi_matched CSV
原 CSV 列 + `Matched_PDF_Paths`（多个匹配路径，分号分隔）+ `Match_Count`（匹配数量）

### 汇总文件

| 文件 | 说明 | 特殊列 |
|------|------|--------|
| `ALL_MATCHED.csv` | 所有期刊匹配成功记录合并 | `Journal`（期刊来源）|
| `ALL_UNMATCHED.csv` | 所有期刊未匹配记录合并 | `Journal`, `DOI_Download_Link`（下载链接）|
| `ALL_MULTI_MATCHED.csv` | 所有期刊多重匹配记录合并 | `Journal`, `DOI_Download_Link` |

**DOI 下载链接**格式为 `https://doi.org/{DOI}`，在 Excel 中点击可直接跳转到出版商页面下载 PDF。

## 重复项检查

脚本在匹配前会自动检查：

1. **PDF 文件名重复**：同一期刊下是否有标准化后相同的文件名
2. **CSV 列重复**：匹配列（Title/DOI）是否有重复值

如果发现重复项，脚本会显示详情并等待用户确认（按 Enter 继续）。

## 日志文件

日志文件保存在 `logs/` 目录，命名格式：`match_log_YYYYMMDD_HHMMSS.log`

日志包含：
- 详细的匹配过程（DEBUG 级别）
- 匹配成功/失败信息（INFO 级别）
- 警告和错误信息

## 测试结果示例

使用 `scopus_dsr.csv`（包含 340 条 Design Science Research 相关记录）对所有期刊进行匹配：

| 期刊 | PDF 数 | 成功匹配 | 匹配率 | 说明 |
|------|--------|---------|--------|------|
| DSS | 68 | 64 | 94% | Title 匹配，有年份 |
| EJIS | 140 | 51 | 36% | Title 匹配，有年份 |
| IM | 22 | 22 | 100% | Title 匹配，有年份 |
| IO | 2 | 2 | 100% | Title 匹配，有年份 |
| ISJ | 72 | 14 | 19% | DOI 匹配 |
| ISR | 841 | 19 | 2% | Title 匹配 + 特殊编码 |
| JAIS | 40 | 36 | 90% | Title 匹配，无年份 |
| JIT | 6 | 5 | 83% | Title 匹配，有年份 |
| JMIS | 110 | 38 | 35% | Title 匹配，无年份 |
| JSIS | 6 | 6 | 100% | Title 匹配，有年份 |
| MISQ | 35 | 26 | 74% | Title 匹配，无年份 |
| **总计** | **1342** | **283** | **21%** | - |

**说明**：
- 匹配率 = 成功匹配数 / PDF 文件数
- 未匹配数较高是因为 CSV 只包含 Design Science Research 相关文献，而 PDF 文件夹包含期刊的其他文献
- ISR 的 PDF 数量特别多（841）但 CSV 中 ISR 文献较少，导致匹配率低

## 常见问题

### Q: 匹配率很低怎么办？
A: 检查以下几点：
- CSV 文件是否包含该期刊的文献记录
- PDF 文件名格式是否符合预期
- 查看日志文件了解详细匹配过程
- 检查 `ALL_UNMATCHED.csv` 中的 `DOI_Download_Link` 手动下载缺失的 PDF

### Q: 如何处理新的期刊？
A: 
- 如果是 DOI 匹配，添加到 `--doi-journals` 参数
- 如果需要特殊编码处理，添加到 `--special-journals` 参数
- 默认使用 Title 匹配（无年份模式）

### Q: 多重匹配如何解决？
A: 
1. 查看 `multi_matched` 或 `ALL_MULTI_MATCHED.csv` 输出
2. 手动检查哪个 PDF 是正确的匹配
3. 删除重复的 PDF 文件后重新运行

### Q: 未匹配的记录如何处理？
A: 
1. 打开 `ALL_UNMATCHED.csv`
2. 点击 `DOI_Download_Link` 列中的链接
3. 在浏览器中下载 PDF 到对应期刊目录
4. 重新运行匹配脚本

## 工作流程建议

1. **准备阶段**
   - 将 PDF 文件按期刊分类放入 `pdfs/` 对应子目录
   - 将 Scopus 导出的 CSV 放入 `scopus_csv_records/`

2. **匹配阶段**
   ```powershell
   uv run match_pdfs_title_doi/match_records.py
   ```

3. **补充阶段**
   - 检查 `ALL_UNMATCHED.csv` 中需要的文献
   - 通过 DOI 链接下载缺失的 PDF
   - 重新运行匹配

4. **后续处理**
   - 使用 `ALL_MATCHED.csv` 中的 `Matched_PDF_Path` 进行 MineRU 批量转换
