#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
文献数据匹配脚本

根据 PDF 文件名匹配 Scopus CSV 记录中的文献数据。
- 默认通过 Title 列进行匹配
- ISJ 文件夹通过 DOI 列进行匹配
- 支持特殊编码文件名的处理（如 ISR 文件夹中的 #x3a; 等编码）

Author: GitHub Copilot
Date: 2025-01-20
"""

import argparse
import csv
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


def setup_logging(log_dir: Path) -> logging.Logger:
    """设置日志记录器"""
    log_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"match_log_{timestamp}.log"
    
    # 创建日志记录器
    logger = logging.getLogger("match_records")
    logger.setLevel(logging.DEBUG)
    
    # 清除已有的处理器（避免重复添加）
    logger.handlers.clear()
    
    # 文件处理器 - 详细日志
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # 控制台处理器 - 简要日志
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def normalize_text(text: str, remove_numbers: bool = True) -> str:
    """
    标准化文本用于匹配：
    - 转为小写
    - 去除所有符号和空格
    - 可选：去除数字
    """
    if not text:
        return ""
    
    # 转为小写
    text = text.lower()
    
    # 只保留字母（和可选的数字）
    if remove_numbers:
        text = re.sub(r'[^a-z]', '', text)
    else:
        text = re.sub(r'[^a-z0-9]', '', text)
    
    return text


def remove_isr_encoding(filename: str) -> str:
    """
    移除 ISR 文件名中的特殊编码
    
    编码格式: #x 后紧跟数字或字母，以 ; 结尾
    例如: #x22; #x3a; #x3f; 等
    
    直接去除这些编码字符
    """
    # 匹配 #x 后跟十六进制字符（数字或a-f），以 ; 结尾
    result = re.sub(r'#x[0-9a-fA-F]+;', '', filename)
    return result


def extract_title_from_pdf_name(pdf_name: str, has_year_pattern: bool = True) -> str:
    """
    从 PDF 文件名中提取标题部分
    
    Args:
        pdf_name: PDF 文件名（不含扩展名）
        has_year_pattern: 是否包含年份模式（如 _2024_期刊名）
    
    文件名格式:
    - 有年份: 标题部分_年份_期刊名部分 (如 DSS, EJIS, IM, IO, JSIS)
    - 无年份: 纯标题 (如 JAIS, MISQ, ISR)
    
    Returns:
        提取的标题部分
    """
    if has_year_pattern:
        # 找到 _年份_ 模式（4位数字前后有下划线）
        match = re.search(r'_(\d{4})_', pdf_name)
        if match:
            # 取年份前的部分作为标题
            return pdf_name[:match.start()]
        
        # 尝试找 _年份 结尾的模式
        match = re.search(r'_(\d{4})$', pdf_name)
        if match:
            return pdf_name[:match.start()]
    
    # 没有年份模式或未找到，使用整个名称
    return pdf_name


def extract_doi_from_pdf_name(pdf_name: str) -> str:
    """
    从 PDF 文件名中提取 DOI
    ISJ 文件名格式: isj.12026, j.1365-2575.2006.00208.x
    """
    # 如果文件名以 isj. 开头
    if pdf_name.startswith('isj.'):
        return f"10.1111/{pdf_name}"
    
    # 如果文件名以 j.1365-2575 开头
    if pdf_name.startswith('j.1365-2575'):
        return f"10.1111/{pdf_name}"
    
    # 如果已经是完整的 DOI 格式
    if pdf_name.startswith('10.'):
        return pdf_name
    
    return pdf_name


def get_pdf_files(base_dir: Path) -> Dict[str, Path]:
    """
    获取指定目录下的所有 PDF 文件
    返回: {文件名（不含扩展名）: 完整路径}
    """
    pdf_files = {}
    try:
        if not base_dir.exists():
            return pdf_files
        
        for item in base_dir.iterdir():
            if item.is_file() and item.suffix.lower() == '.pdf':
                # 使用不含扩展名的文件名作为键
                name_without_ext = item.stem
                pdf_files[name_without_ext] = item
    except Exception as e:
        logging.getLogger("match_records").error(f"读取目录 {base_dir} 时出错: {e}")
    
    return pdf_files


def read_csv_records(csv_path: Path) -> Tuple[List[Dict], List[str]]:
    """
    读取 CSV 文件记录
    返回: (记录列表, 表头列表)
    """
    records = []
    headers = []
    
    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            for row in reader:
                records.append(row)
    except Exception as e:
        logging.getLogger("match_records").error(f"读取 CSV 文件 {csv_path} 时出错: {e}")
        raise
    
    return records, headers


def check_duplicates_in_files(
    files: Dict[str, Path],
    logger: logging.Logger,
    keep_numbers: bool = False
) -> List[str]:
    """
    检查文件名是否有重复（标准化后）
    
    Args:
        files: 文件名到路径的映射
        logger: 日志记录器
        keep_numbers: 是否保留数字（DOI 匹配时应为 True）
    
    返回重复的文件名列表
    """
    name_counts = defaultdict(list)
    
    for name, path in files.items():
        # 使用标准化名称检查重复
        normalized = normalize_text(name, remove_numbers=not keep_numbers)
        name_counts[normalized].append((name, str(path)))
    
    duplicates = []
    for normalized, items in name_counts.items():
        if len(items) > 1:
            duplicates.append(f"  标准化名 '{normalized}': {[item[0] for item in items]}")
    
    return duplicates


def check_duplicates_in_csv(
    records: List[Dict],
    column: str,
    logger: logging.Logger,
    keep_numbers: bool = False
) -> List[str]:
    """
    检查 CSV 中指定列是否有重复值
    
    Args:
        records: CSV 记录列表
        column: 要检查的列名
        logger: 日志记录器
        keep_numbers: 是否保留数字（DOI 匹配时应为 True）
    
    返回重复的值列表
    """
    value_counts = defaultdict(int)
    
    for record in records:
        value = record.get(column, "")
        if value:
            normalized = normalize_text(value, remove_numbers=not keep_numbers)
            value_counts[normalized] += 1
    
    duplicates = []
    for value, count in value_counts.items():
        if count > 1:
            # 找到原始值
            for record in records:
                orig_value = record.get(column, "")
                if normalize_text(orig_value, remove_numbers=not keep_numbers) == value:
                    duplicates.append(f"  '{orig_value[:60]}...' (出现 {count} 次)")
                    break
    
    return duplicates


def match_pdfs_to_records(
    pdf_files: Dict[str, Path],
    records: List[Dict],
    match_column: str,
    use_doi_matching: bool = False,
    use_special_encoding: bool = False,
    has_year_pattern: bool = True,
    logger: Optional[logging.Logger] = None
) -> Tuple[Dict[int, Path], List[int], List[Tuple[int, List[Path]]]]:
    """
    将 PDF 文件匹配到 CSV 记录
    
    Args:
        pdf_files: PDF 文件名到路径的映射
        records: CSV 记录列表
        match_column: 要匹配的列名 (Title 或 DOI)
        use_doi_matching: 是否使用 DOI 匹配（针对 ISJ）
        use_special_encoding: 是否处理特殊编码（针对 ISR）
        has_year_pattern: 文件名是否包含年份模式
        logger: 日志记录器
    
    Returns:
        matched: {记录索引: 匹配的 PDF 路径}
        unmatched: 未匹配的记录索引列表
        multi_matched: [(记录索引, [匹配的多个 PDF 路径])]
    """
    if logger is None:
        logger = logging.getLogger("match_records")
    
    matched = {}
    unmatched = []
    multi_matched = []
    
    # 预处理 PDF 文件名
    pdf_normalized_map = {}  # {标准化名称: [(原始名称, 路径)]}
    
    for pdf_name, pdf_path in pdf_files.items():
        # 获取用于匹配的文本
        if use_doi_matching:
            # DOI 匹配：从文件名提取 DOI
            match_text = extract_doi_from_pdf_name(pdf_name)
            normalized = normalize_text(match_text, remove_numbers=False)
        else:
            # Title 匹配
            # 先处理特殊编码（如 ISR）
            processed_name = pdf_name
            if use_special_encoding:
                processed_name = remove_isr_encoding(processed_name)
            
            # 提取标题部分（根据是否有年份模式）
            title_part = extract_title_from_pdf_name(processed_name, has_year_pattern)
            normalized = normalize_text(title_part)
        
        if normalized not in pdf_normalized_map:
            pdf_normalized_map[normalized] = []
        pdf_normalized_map[normalized].append((pdf_name, pdf_path))
        
        logger.debug(f"PDF 标准化: '{pdf_name}' -> '{normalized}'")
    
    # 遍历每条记录进行匹配
    for idx, record in enumerate(records):
        column_value = record.get(match_column, "")
        
        if not column_value:
            logger.warning(f"记录 {idx + 1}: {match_column} 列为空")
            unmatched.append(idx)
            continue
        
        # 标准化记录值
        if use_doi_matching:
            record_normalized = normalize_text(column_value, remove_numbers=False)
        else:
            record_normalized = normalize_text(column_value)
        
        logger.debug(f"记录 {idx + 1} {match_column} 标准化: '{column_value[:50]}...' -> '{record_normalized[:50]}...'")
        
        # 查找匹配的 PDF
        # 匹配逻辑：PDF 文件名必须完全被 CSV 内容从头开始包含
        # 即 CSV 内容的标准化版本必须以 PDF 文件名的标准化版本开头
        matching_pdfs = []
        
        for pdf_normalized, pdf_list in pdf_normalized_map.items():
            # 检查记录值是否从头开始包含 PDF 文件名（文件名被完全匹配）
            if pdf_normalized and record_normalized.startswith(pdf_normalized):
                matching_pdfs.extend([path for _, path in pdf_list])
        
        # 处理匹配结果
        if len(matching_pdfs) == 0:
            logger.debug(f"记录 {idx + 1}: 未找到匹配的 PDF")
            unmatched.append(idx)
        elif len(matching_pdfs) == 1:
            logger.info(f"记录 {idx + 1}: 成功匹配到 '{matching_pdfs[0].name}'")
            matched[idx] = matching_pdfs[0]
        else:
            logger.warning(f"记录 {idx + 1}: 匹配到多个 PDF: {[f.name for f in matching_pdfs]}")
            multi_matched.append((idx, matching_pdfs))
    
    return matched, unmatched, multi_matched


def save_matched_csv(
    records: List[Dict],
    headers: List[str],
    matched: Dict[int, Path],
    output_path: Path,
    logger: logging.Logger
) -> None:
    """保存成功匹配的 CSV 文件"""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 添加新列
        new_headers = headers + ['Matched_PDF_Path']
        
        matched_records = []
        for idx, path in matched.items():
            record = records[idx].copy()
            record['Matched_PDF_Path'] = str(path)
            matched_records.append(record)
        
        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=new_headers)
            writer.writeheader()
            writer.writerows(matched_records)
        
        logger.info(f"成功保存匹配结果到: {output_path} ({len(matched_records)} 条记录)")
    except Exception as e:
        logger.error(f"保存匹配 CSV 时出错: {e}")
        raise


def save_unmatched_csv(
    records: List[Dict],
    headers: List[str],
    unmatched_indices: List[int],
    output_path: Path,
    reason: str,
    logger: logging.Logger
) -> None:
    """保存未匹配的 CSV 文件"""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 添加原因列
        new_headers = headers + ['Unmatch_Reason']
        
        unmatched_records = []
        for idx in unmatched_indices:
            record = records[idx].copy()
            record['Unmatch_Reason'] = reason
            unmatched_records.append(record)
        
        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=new_headers)
            writer.writeheader()
            writer.writerows(unmatched_records)
        
        logger.info(f"保存未匹配结果到: {output_path} ({len(unmatched_records)} 条记录)")
    except Exception as e:
        logger.error(f"保存未匹配 CSV 时出错: {e}")
        raise


def save_multi_matched_csv(
    records: List[Dict],
    headers: List[str],
    multi_matched: List[Tuple[int, List[Path]]],
    output_path: Path,
    logger: logging.Logger
) -> None:
    """保存多重匹配的 CSV 文件"""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 添加新列
        new_headers = headers + ['Matched_PDF_Paths', 'Match_Count']
        
        multi_records = []
        for idx, paths in multi_matched:
            record = records[idx].copy()
            record['Matched_PDF_Paths'] = '; '.join([str(p) for p in paths])
            record['Match_Count'] = len(paths)
            multi_records.append(record)
        
        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=new_headers)
            writer.writeheader()
            writer.writerows(multi_records)
        
        logger.info(f"保存多重匹配结果到: {output_path} ({len(multi_records)} 条记录)")
    except Exception as e:
        logger.error(f"保存多重匹配 CSV 时出错: {e}")
        raise


def generate_doi_url(doi: str) -> str:
    """
    根据 DOI 生成下载链接
    
    Args:
        doi: DOI 字符串
    
    Returns:
        下载 URL
    """
    if not doi or not doi.strip():
        return ""
    
    doi = doi.strip()
    
    # 如果已经是完整 URL，直接返回
    if doi.startswith('http'):
        return doi
    
    # 生成 doi.org 链接
    return f"https://doi.org/{doi}"


def merge_csv_files(
    input_dir: Path,
    output_path: Path,
    add_journal_column: bool = True,
    add_doi_link: bool = False,
    deduplicate: bool = False,
    dedup_key: str = 'DOI',
    exclude_keys: Optional[Set[str]] = None,
    logger: Optional[logging.Logger] = None
) -> int:
    """
    合并目录下所有 CSV 文件到一个文件
    
    Args:
        input_dir: 包含 CSV 文件的目录
        output_path: 输出文件路径
        add_journal_column: 是否添加期刊来源列
        add_doi_link: 是否添加 DOI 下载链接列
        deduplicate: 是否去重
        dedup_key: 去重依据的列名
        exclude_keys: 要排除的键值集合（用于排除已匹配的记录）
        logger: 日志记录器
    
    Returns:
        合并的记录总数
    """
    if logger is None:
        logger = logging.getLogger("match_records")
    
    if exclude_keys is None:
        exclude_keys = set()
    
    all_records = []
    all_headers = None
    seen_keys = set()  # 用于去重
    
    # 读取所有 CSV 文件
    csv_files = sorted(input_dir.glob("*.csv"))
    
    for csv_file in csv_files:
        try:
            with open(csv_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames or []
                
                # 从文件名提取期刊名（如 DSS_matched.csv -> DSS）
                journal_name = csv_file.stem.split('_')[0]
                
                for row in reader:
                    # 获取键值
                    key = row.get(dedup_key, '')
                    
                    # 排除已匹配的记录
                    if key in exclude_keys:
                        continue
                    
                    # 去重检查
                    if deduplicate:
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                    
                    if add_journal_column:
                        row['Journal'] = journal_name
                    
                    if add_doi_link:
                        doi = row.get('DOI', '')
                        row['DOI_Download_Link'] = generate_doi_url(doi)
                    
                    all_records.append(row)
                
                # 记录第一个文件的表头作为基准
                if all_headers is None:
                    all_headers = list(headers)
                    if add_journal_column:
                        all_headers.insert(0, 'Journal')
                    if add_doi_link:
                        all_headers.append('DOI_Download_Link')
        
        except Exception as e:
            logger.warning(f"读取 {csv_file} 失败: {e}")
    
    if not all_records:
        logger.warning(f"没有找到任何记录可合并")
        return 0
    
    # 写入合并文件
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=all_headers, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(all_records)
        
        logger.info(f"合并完成: {output_path} ({len(all_records)} 条记录)")
        return len(all_records)
    
    except Exception as e:
        logger.error(f"保存合并 CSV 时出错: {e}")
        return 0


# 定义期刊的文件名模式
# has_year: 文件名是否包含年份模式 (_年份_期刊名)
JOURNAL_PATTERNS = {
    'DSS': {'has_year': True, 'use_doi': False, 'special_encoding': False},
    'EJIS': {'has_year': True, 'use_doi': False, 'special_encoding': False},
    'IM': {'has_year': True, 'use_doi': False, 'special_encoding': False},
    'IO': {'has_year': True, 'use_doi': False, 'special_encoding': False},
    'JSIS': {'has_year': True, 'use_doi': False, 'special_encoding': False},
    'JIT': {'has_year': True, 'use_doi': False, 'special_encoding': False},
    'ISJ': {'has_year': False, 'use_doi': True, 'special_encoding': False},
    'ISR': {'has_year': False, 'use_doi': False, 'special_encoding': True},
    'JAIS': {'has_year': False, 'use_doi': False, 'special_encoding': False},
    'JMIS': {'has_year': False, 'use_doi': False, 'special_encoding': False},
    'MISQ': {'has_year': False, 'use_doi': False, 'special_encoding': False},
}


def get_journal_pattern(journal_name: str, doi_journals: Set[str], special_journals: Set[str]) -> dict:
    """
    获取期刊的文件名模式配置
    
    优先使用预定义模式，然后根据命令行参数覆盖
    """
    journal_upper = journal_name.upper()
    
    # 获取预定义模式或默认值
    if journal_upper in JOURNAL_PATTERNS:
        pattern = JOURNAL_PATTERNS[journal_upper].copy()
    else:
        # 默认模式：有年份，Title 匹配，无特殊编码
        pattern = {'has_year': True, 'use_doi': False, 'special_encoding': False}
    
    # 根据命令行参数覆盖
    if journal_upper in [j.upper() for j in doi_journals]:
        pattern['use_doi'] = True
    if journal_upper in [j.upper() for j in special_journals]:
        pattern['special_encoding'] = True
    
    return pattern


def process_journal(
    journal_name: str,
    csv_path: Path,
    pdfs_dir: Path,
    output_base_dir: Path,
    doi_journals: Set[str],
    special_journals: Set[str],
    logger: logging.Logger
) -> Dict[str, int]:
    """
    处理单个期刊的匹配
    
    Returns:
        统计信息字典
    """
    stats = {
        'total_records': 0,
        'total_pdfs': 0,
        'matched': 0,
        'unmatched': 0,
        'multi_matched': 0
    }
    
    logger.info(f"\n{'='*60}")
    logger.info(f"开始处理期刊: {journal_name}")
    logger.info(f"{'='*60}")
    
    try:
        # 读取 CSV
        records, headers = read_csv_records(csv_path)
        stats['total_records'] = len(records)
        logger.info(f"读取到 {len(records)} 条 CSV 记录")
        
        # 获取 PDF 文件
        pdf_files = get_pdf_files(pdfs_dir)
        stats['total_pdfs'] = len(pdf_files)
        logger.info(f"找到 {len(pdf_files)} 个 PDF 文件")
        
        if not pdf_files:
            logger.warning(f"未找到任何 PDF 文件，跳过 {journal_name}")
            stats['unmatched'] = len(records)
            return stats
        
        # 获取期刊模式配置
        pattern = get_journal_pattern(journal_name, doi_journals, special_journals)
        
        use_doi = pattern['use_doi']
        use_special = pattern['special_encoding']
        has_year = pattern['has_year']
        match_column = 'DOI' if use_doi else 'Title'
        
        logger.info(f"匹配模式: {'DOI 匹配' if use_doi else 'Title 匹配'}")
        logger.info(f"文件名格式: {'含年份' if has_year else '纯标题'}")
        if use_special:
            logger.info("启用特殊编码处理")
        
        # 检查重复
        logger.info("检查重复项...")
        
        # DOI 匹配时需要保留数字
        keep_numbers = use_doi
        
        # 检查 PDF 文件名重复（标准化后）
        pdf_dups = check_duplicates_in_files(pdf_files, logger, keep_numbers=keep_numbers)
        if pdf_dups:
            logger.warning(f"发现标准化后重复的 PDF 文件名:")
            for dup in pdf_dups:
                logger.warning(dup)
            print(f"\n⚠️ 发现 {len(pdf_dups)} 组标准化后重复的 PDF 文件名:")
            for dup in pdf_dups:
                print(dup)
            input("按 Enter 继续...")
        else:
            logger.info("PDF 文件名无重复")
        
        # 检查 CSV 列重复
        csv_dups = check_duplicates_in_csv(records, match_column, logger, keep_numbers=keep_numbers)
        if csv_dups:
            logger.warning(f"发现重复的 {match_column} 值:")
            for dup in csv_dups[:10]:  # 只显示前10个
                logger.warning(dup)
            if len(csv_dups) > 10:
                logger.warning(f"  ... 还有 {len(csv_dups) - 10} 个重复项")
            print(f"\n⚠️ 发现 {len(csv_dups)} 个重复的 {match_column} 值:")
            for dup in csv_dups[:10]:
                print(dup)
            if len(csv_dups) > 10:
                print(f"  ... 还有 {len(csv_dups) - 10} 个重复项")
            input("按 Enter 继续...")
        else:
            logger.info(f"{match_column} 列无重复")
        
        # 执行匹配
        logger.info("开始匹配...")
        matched, unmatched, multi_matched = match_pdfs_to_records(
            pdf_files=pdf_files,
            records=records,
            match_column=match_column,
            use_doi_matching=use_doi,
            use_special_encoding=use_special,
            has_year_pattern=has_year,
            logger=logger
        )
        
        stats['matched'] = len(matched)
        stats['unmatched'] = len(unmatched)
        stats['multi_matched'] = len(multi_matched)
        
        # 创建输出目录
        matched_dir = output_base_dir / "matched"
        unmatched_dir = output_base_dir / "unmatched"
        multi_matched_dir = output_base_dir / "multi_matched"
        
        # 保存结果
        if matched:
            save_matched_csv(
                records=records,
                headers=headers,
                matched=matched,
                output_path=matched_dir / f"{journal_name}_matched.csv",
                logger=logger
            )
        
        if unmatched:
            save_unmatched_csv(
                records=records,
                headers=headers,
                unmatched_indices=unmatched,
                output_path=unmatched_dir / f"{journal_name}_unmatched.csv",
                reason="未找到匹配的 PDF 文件",
                logger=logger
            )
        
        if multi_matched:
            save_multi_matched_csv(
                records=records,
                headers=headers,
                multi_matched=multi_matched,
                output_path=multi_matched_dir / f"{journal_name}_multi_matched.csv",
                logger=logger
            )
        
        # 打印统计
        logger.info(f"\n{journal_name} 匹配统计:")
        logger.info(f"  CSV 记录数: {stats['total_records']}")
        logger.info(f"  PDF 文件数: {stats['total_pdfs']}")
        logger.info(f"  成功匹配: {stats['matched']}")
        logger.info(f"  未匹配:   {stats['unmatched']}")
        logger.info(f"  多重匹配: {stats['multi_matched']}")
        
    except Exception as e:
        logger.error(f"处理 {journal_name} 时发生错误: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise
    
    return stats


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='匹配文献数据：将 pdfs 文件夹中的 PDF 文件名与 Scopus CSV 记录匹配',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python match_records.py
  python match_records.py --input-dir ../pdfs --csv-dir ./scopus_csv_records
  python match_records.py --doi-journals ISJ --special-journals ISR
        """
    )
    
    # 路径参数
    parser.add_argument(
        '--input-dir',
        type=str,
        default='../pdfs',
        help='输入目录，包含期刊子文件夹和 PDF 文件 (默认: ../pdfs)'
    )
    parser.add_argument(
        '--csv-dir',
        type=str,
        default='./scopus_csv_records',
        help='CSV 文件目录 (默认: ./scopus_csv_records)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='./match_results',
        help='输出目录 (默认: ./match_results)'
    )
    parser.add_argument(
        '--log-dir',
        type=str,
        default='./logs',
        help='日志目录 (默认: ./logs)'
    )
    
    # 匹配模式参数
    parser.add_argument(
        '--doi-journals',
        type=str,
        default='ISJ',
        help='使用 DOI 匹配的期刊列表，逗号分隔 (默认: ISJ)'
    )
    parser.add_argument(
        '--special-journals',
        type=str,
        default='ISR',
        help='需要特殊编码处理的期刊列表，逗号分隔 (默认: ISR)'
    )
    
    # 可选参数
    parser.add_argument(
        '--journals',
        type=str,
        default=None,
        help='要处理的期刊列表，逗号分隔 (默认: 处理所有在 input-dir 中找到的期刊)'
    )
    parser.add_argument(
        '--csv-pattern',
        type=str,
        default='scopus_*.csv',
        help='CSV 文件名模式 (默认: scopus_*.csv)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='仅检查，不保存结果'
    )
    
    args = parser.parse_args()
    
    # 转换路径
    script_dir = Path(__file__).parent
    input_dir = Path(args.input_dir)
    if not input_dir.is_absolute():
        input_dir = (script_dir / input_dir).resolve()
    
    csv_dir = Path(args.csv_dir)
    if not csv_dir.is_absolute():
        csv_dir = (script_dir / csv_dir).resolve()
    
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = (script_dir / output_dir).resolve()
    
    log_dir = Path(args.log_dir)
    if not log_dir.is_absolute():
        log_dir = (script_dir / log_dir).resolve()
    
    # 设置日志
    logger = setup_logging(log_dir)
    logger.info("="*60)
    logger.info("文献数据匹配脚本启动 (PDF 文件名匹配模式)")
    logger.info("="*60)
    logger.info(f"输入目录: {input_dir}")
    logger.info(f"CSV 目录: {csv_dir}")
    logger.info(f"输出目录: {output_dir}")
    logger.info(f"日志目录: {log_dir}")
    
    # 解析特殊期刊列表
    doi_journals = set(j.strip().upper() for j in args.doi_journals.split(',') if j.strip())
    special_journals = set(j.strip().upper() for j in args.special_journals.split(',') if j.strip())
    
    logger.info(f"DOI 匹配期刊: {doi_journals}")
    logger.info(f"特殊编码期刊: {special_journals}")
    
    # 显示已知期刊模式
    logger.info("已知期刊文件名模式:")
    for j, p in JOURNAL_PATTERNS.items():
        mode = "DOI" if p['use_doi'] else "Title"
        year = "有年份" if p['has_year'] else "无年份"
        special = " + 特殊编码" if p['special_encoding'] else ""
        logger.info(f"  {j}: {mode} 匹配, {year}{special}")
    
    # 验证目录
    if not input_dir.exists():
        logger.error(f"输入目录不存在: {input_dir}")
        sys.exit(1)
    
    if not csv_dir.exists():
        logger.error(f"CSV 目录不存在: {csv_dir}")
        sys.exit(1)
    
    # 获取要处理的期刊
    if args.journals:
        journals_to_process = [j.strip() for j in args.journals.split(',')]
    else:
        # 自动发现期刊目录
        journals_to_process = []
        for item in input_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                journals_to_process.append(item.name)
    
    logger.info(f"待处理期刊: {journals_to_process}")
    
    # 查找 CSV 文件
    csv_files = list(csv_dir.glob(args.csv_pattern))
    
    # 创建期刊到 CSV 文件的映射
    journal_csv_map = {}
    
    # 如果只有一个 CSV 文件，处理所有期刊使用同一个 CSV
    if len(csv_files) == 1:
        logger.info(f"找到单个 CSV 文件: {csv_files[0]}")
        for journal in journals_to_process:
            journal_csv_map[journal] = csv_files[0]
    else:
        # 尝试按期刊名匹配
        for csv_file in csv_files:
            stem = csv_file.stem.lower()
            for journal in journals_to_process:
                journal_lower = journal.lower()
                if journal_lower in stem or stem.endswith(journal_lower):
                    journal_csv_map[journal] = csv_file
                    break
    
    logger.info(f"期刊-CSV 映射: {[(j, str(c.name)) for j, c in journal_csv_map.items()]}")
    
    # 处理每个期刊
    all_stats = {}
    
    for journal in journals_to_process:
        csv_file = journal_csv_map.get(journal)
        
        if not csv_file:
            logger.warning(f"未找到期刊 {journal} 对应的 CSV 文件，跳过")
            continue
        
        pdfs_dir = input_dir / journal
        
        if not pdfs_dir.exists():
            logger.warning(f"期刊目录不存在: {pdfs_dir}，跳过")
            continue
        
        try:
            stats = process_journal(
                journal_name=journal,
                csv_path=csv_file,
                pdfs_dir=pdfs_dir,
                output_base_dir=output_dir,
                doi_journals=doi_journals,
                special_journals=special_journals,
                logger=logger
            )
            all_stats[journal] = stats
        except Exception as e:
            logger.error(f"处理期刊 {journal} 失败: {e}")
            all_stats[journal] = {'error': str(e)}
    
    # 打印总结
    logger.info("\n" + "="*60)
    logger.info("匹配总结")
    logger.info("="*60)
    
    total_records = 0
    total_pdfs = 0
    total_matched = 0
    total_unmatched = 0
    total_multi = 0
    
    for journal, stats in all_stats.items():
        if 'error' in stats:
            logger.info(f"{journal}: 处理失败 - {stats['error']}")
        else:
            logger.info(f"{journal}: CSV {stats['total_records']} 条, "
                       f"PDF {stats['total_pdfs']} 个, "
                       f"匹配 {stats['matched']}, "
                       f"未匹配 {stats['unmatched']}, "
                       f"多重 {stats['multi_matched']}")
            total_records += stats['total_records']
            total_pdfs += stats['total_pdfs']
            total_matched += stats['matched']
            total_unmatched += stats['unmatched']
            total_multi += stats['multi_matched']
    
    logger.info("-"*40)
    logger.info(f"总计: {total_records} 条 CSV 记录, {total_pdfs} 个 PDF 文件")
    logger.info(f"  成功匹配: {total_matched} ({100*total_matched/max(total_records,1):.1f}%)")
    logger.info(f"  未匹配:   {total_unmatched} ({100*total_unmatched/max(total_records,1):.1f}%)")
    logger.info(f"  多重匹配: {total_multi} ({100*total_multi/max(total_records,1):.1f}%)")
    
    # 合并所有结果到汇总 CSV
    logger.info("\n" + "="*60)
    logger.info("生成汇总文件")
    logger.info("="*60)
    
    matched_dir = output_dir / "matched"
    unmatched_dir = output_dir / "unmatched"
    multi_matched_dir = output_dir / "multi_matched"
    
    # 合并所有匹配成功的记录，并收集已匹配的 DOI
    matched_dois = set()
    if matched_dir.exists():
        all_matched_path = output_dir / "ALL_MATCHED.csv"
        matched_count = merge_csv_files(
            input_dir=matched_dir,
            output_path=all_matched_path,
            add_journal_column=True,
            add_doi_link=False,
            logger=logger
        )
        if matched_count > 0:
            logger.info(f"✅ 所有匹配成功记录已合并到: {all_matched_path}")
            # 收集已匹配的 DOI
            try:
                with open(all_matched_path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        doi = row.get('DOI', '')
                        if doi:
                            matched_dois.add(doi)
                logger.info(f"   已收集 {len(matched_dois)} 个已匹配的 DOI")
            except Exception as e:
                logger.warning(f"收集已匹配 DOI 时出错: {e}")
    
    # 合并所有未匹配的记录（添加 DOI 下载链接，去重，并排除已匹配的）
    if unmatched_dir.exists():
        all_unmatched_path = output_dir / "ALL_UNMATCHED.csv"
        unmatched_count = merge_csv_files(
            input_dir=unmatched_dir,
            output_path=all_unmatched_path,
            add_journal_column=False,  # 去重后期刊来源无意义
            add_doi_link=True,  # 为未匹配记录添加下载链接
            deduplicate=True,  # 按 DOI 去重
            dedup_key='DOI',
            exclude_keys=matched_dois,  # 排除已匹配的 DOI
            logger=logger
        )
        if unmatched_count > 0:
            logger.info(f"❌ 所有未匹配记录已合并到: {all_unmatched_path}")
            logger.info(f"   已按 DOI 去重并排除已匹配项，共 {unmatched_count} 条记录需要下载")
            logger.info(f"   已添加 DOI_Download_Link 列，可直接打开链接下载")
    
    # 合并所有多重匹配的记录
    if multi_matched_dir.exists() and list(multi_matched_dir.glob("*.csv")):
        all_multi_path = output_dir / "ALL_MULTI_MATCHED.csv"
        multi_count = merge_csv_files(
            input_dir=multi_matched_dir,
            output_path=all_multi_path,
            add_journal_column=True,
            add_doi_link=True,
            logger=logger
        )
        if multi_count > 0:
            logger.info(f"⚠️ 所有多重匹配记录已合并到: {all_multi_path}")
    
    logger.info("\n处理完成！")


if __name__ == '__main__':
    main()
