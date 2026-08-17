# -*- coding: utf-8 -*-
"""
scripts/deep_split_checklists.py
L2：粗粒度检查项深拆 —— 生成管理员确认单 + 应用到模板 parsed_structure

背景：
  检查清单按句切分后，部分节点的单条检查项内含 5~15 个字段
  （如 n17 技术参数 132 字一条）。一条多项导致 LLM "漏一个字段"
  仍判 pass，首跑召回不足。本脚本把这些粗粒度项逐字段拆开，
  写入节点显式 check_items（checklist.split_check_items 优先读取）。

用法：
  # 1) 生成确认单（桌面 docx + _debug_sr/deep_split_proposal.json）
  python scripts/deep_split_checklists.py --sheet

  # 2) 管理员在 JSON 中删掉不同意的拆分（删除对应节点键即可）后应用：
  python scripts/deep_split_checklists.py --apply --base http://localhost:5173

应用走本地 API：GET/PUT /api/scheme-types/{sid}/template/structure
（PUT 需要管理员 token，脚本用 admin 登录获取）。
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROPOSAL_PATH = REPO / "_debug_sr" / "deep_split_proposal.json"
SHEET_PATH = Path(r"C:\Users\Administrator\Desktop\SmartReview检查项深拆确认单.docx")

# ---------------------------------------------------------------------------
# 人工编排的深拆方案（基于 backups/template_12_parsed_structure_backup_20260815.json）
# 原则：只拆不增——每条拆分项的文字均取自原 review_prompt，不引入新要求。
# ---------------------------------------------------------------------------
DEEP_SPLIT: dict[str, dict] = {
    "n2": {
        "title": "1.脚手架工程概况和特点",
        "items": [
            {"id": "n2-1", "text": "核对是否含有本项目工程概况"},
            {"id": "n2-2", "text": "核对是否含有悬挑脚手架工程概况（悬挑脚手架搭设区域与范围，搭设起止标高、总搭设高度，悬挑长度，立杆纵/横距、步距等）"},
            {"id": "n2-3", "text": "核对是否含有工程及周边环境情况描述"},
            {"id": "n2-4", "text": "核对是否明确属于危险性较大的分部分项工程还是超过一定规模的危险性较大的分部分项工程"},
        ],
    },
    "n6": {
        "title": "5.风险辨识与分级",
        "items": [
            {"id": "n6-1", "text": "核对是否明确风险因素辨识（如坍塌、高处坠落、物体打击、触电等）"},
            {"id": "n6-2", "text": "核对是否含有悬挑脚手架体系安全风险分级"},
            {"id": "n6-3", "text": "需对照风险逐条写出针对性的应对管控措施，若无施工风险辨识、风险分级及相应的风险管控措施方案，则属于严重缺陷"},
        ],
    },
    "n13": {
        "title": "1.施工进度计划",
        "items": [
            {"id": "n13-1", "text": "核对是否含有悬挑脚手架工程的施工进度安排"},
            {"id": "n13-2", "text": "进度安排应具体到细致的工序，包括预埋锚环、工字钢主梁与联梁安装、架体与脚手板搭设、钢丝绳张拉等"},
        ],
    },
    "n14": {
        "title": "2.材料与设备计划",
        "items": [
            {"id": "n14-1", "text": "核对是否含有悬挑脚手架选用材料的规格型号"},
            {"id": "n14-2", "text": "核对是否含有所用设备的规格型号"},
            {"id": "n14-3", "text": "核对是否含有材料和设备的数量及材料和设备进退场时间计划安排"},
        ],
    },
    "n17": {
        "title": "1.技术参数",
        "items": [
            {"id": "n17-1", "text": "核对是否含有悬挑脚手架所用材料选型、材料规格及材料质量要求（悬挑工字钢、钢管、钢丝绳、预埋锚环等所有构配件规格、材质质量要求）"},
            {"id": "n17-2", "text": "核对是否含有脚手架搭设排数、脚手架钢管类型"},
            {"id": "n17-3", "text": "核对是否含有脚手架架体高度、步距、立杆纵距或跨距、立杆横距"},
            {"id": "n17-4", "text": "核对是否含有连墙件布置方式"},
            {"id": "n17-5", "text": "核对是否含有工字钢主梁间距、主梁与建筑物连接方式、锚固点设置方式、锚环直径"},
            {"id": "n17-6", "text": "核对是否含有主梁建筑物外悬挑长度、主梁建筑物内锚固长度、梁/楼板混凝土强度等级"},
            {"id": "n17-7", "text": "若采用禁止的设备和材料，则为严重缺陷"},
        ],
    },
    "n18": {
        "title": "2.工艺流程",
        "items": [
            {"id": "n18-1", "text": "核对是否含有悬挑脚手架搭设工艺流程（参考：锚环预埋->工字钢主梁与联梁安装固定->底部硬质封闭->钢丝绳/拉杆安装与初步张拉->架体、连墙件、剪刀撑安装->脚手板、防护栏杆、挡脚板搭设->安全网封闭->钢丝绳最终张拉）"},
            {"id": "n18-2", "text": "核对是否含有悬挑脚手架使用阶段的工艺要求"},
            {"id": "n18-3", "text": "核对是否含有悬挑脚手架拆除工艺流程"},
            {"id": "n18-4", "text": "若未明确施工工艺，则属于严重缺陷，如果判断属于严重缺陷，那么属于严重缺陷这句话一定要指出来"},
        ],
    },
    "n19": {
        "title": "3.施工方法及操作要求",
        "items": [
            {"id": "n19-1", "text": "请检查是否含有脚手架搭设标准、剪刀撑、周边拉结等各类构造措施内容"},
            {"id": "n19-2", "text": "请检查是否含有安全防护搭设、脚手架安装、日常使用、拆除作业全流程操作要点"},
            {"id": "n19-3", "text": "若高度超过20米的悬挑脚手架无架体卸荷措施，属于严重缺陷"},
        ],
    },
    "n20": {
        "title": "4.检查要求",
        "items": [
            {"id": "n20-1", "text": "请检查是否明确工字钢、钢管、扣件、钢丝绳等脚手架主材进场外观、尺寸等质量检查标准"},
            {"id": "n20-2", "text": "请检查是否完整列明各阶段检查节点、各节点对应的检查项目与核查内容"},
        ],
    },
    "n24": {
        "title": "3.监测监控措施",
        "items": [
            {"id": "n24-1", "text": "核对是否含有监测组织机构、监测范围、监测项目（如架体稳定性）、监测方法、监测频率、预警值及控制值"},
            {"id": "n24-2", "text": "核对是否含有巡视检查、信息反馈"},
            {"id": "n24-3", "text": "核对是否含有监测点布置图"},
        ],
    },
    "n32": {
        "title": "2.验收程序",
        "items": [
            {"id": "n32-1", "text": "核对是否含有具体验收程序"},
            {"id": "n32-2", "text": "核对是否含有验收人员组成（建设、设计、施工、监理、监测等单位相关负责人）"},
            {"id": "n32-3", "text": "具体人员组成及专家数量应满足“住房城乡建设部办公厅关于实施《危险性较大的分部分项工程安全管理规定》有关问题的通知”文件中的要求"},
        ],
    },
    "n33": {
        "title": "3.验收内容",
        "items": [
            {"id": "n33-1", "text": "核对是否含有工字钢材料质量验收内容"},
            {"id": "n33-2", "text": "核对是否含有进场钢管、扣件材料质量验收内容"},
            {"id": "n33-3", "text": "核对是否含有架体构造验收内容"},
            {"id": "n33-4", "text": "核对是否含有连墙件与拉结钢丝绳验收内容"},
            {"id": "n33-5", "text": "核对是否含有外立面剪刀撑验收内容"},
        ],
    },
    "n41": {
        "title": "2.相关施工图纸",
        "items": [
            {"id": "n41-1", "text": "核对是否含有脚手架平面布置图"},
            {"id": "n41-2", "text": "核对是否含有脚手架立（剖）面图（含剪刀撑布置）"},
            {"id": "n41-3", "text": "核对是否含有悬挑构件点位布置平面图"},
            {"id": "n41-4", "text": "核对是否含有连墙件布置图"},
            {"id": "n41-5", "text": "如果1.2节“施工平面及立面布置”含有以上图，则该小节无需含有（判定前需核对1.2节）"},
        ],
    },
}


# ---------------------------------------------------------------------------
def build_sheet() -> None:
    """生成桌面 docx 确认单 + JSON 提案文件"""
    PROPOSAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROPOSAL_PATH.write_text(
        json.dumps(DEEP_SPLIT, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    from docx import Document
    from docx.oxml.ns import qn
    from docx.shared import Pt

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "微软雅黑"
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    style.font.size = Pt(10.5)

    doc.add_heading("SmartReview 检查项深拆确认单（模板12·悬挑脚手架）", level=1)
    p = doc.add_paragraph(
        "说明：下列节点的检查项由粗粒度（一条含多个字段）深拆为逐字段检查。"
        "拆分文字均取自原审核提示词，未新增要求。请确认后把 "
        "_debug_sr/deep_split_proposal.json 中不同意的节点整键删除，"
        "再执行 --apply。"
    )
    total_before = 0
    total_after = 0
    for node_id, spec in DEEP_SPLIT.items():
        total_after += len(spec["items"])
        doc.add_heading(f"{node_id} {spec['title']}", level=2)
        for it in spec["items"]:
            doc.add_paragraph(f"[{it['id']}] {it['text']}")

    # 统计拆分前条数（读备份）
    backup = REPO / "backups" / "template_12_parsed_structure_backup_20260815.json"
    if backup.exists():
        sys.path.insert(0, str(REPO / "backend"))
        from app.services.checklist import split_check_items  # noqa: WPS433

        data = json.loads(backup.read_text(encoding="utf-8"))

        def walk(nodes: list) -> None:
            nonlocal total_before
            for n in nodes:
                tid = str(n.get("id") or "")
                if tid in DEEP_SPLIT and n.get("review_prompt"):
                    items, _ = split_check_items(tid, n["review_prompt"])
                    total_before += len(items)
                walk(n.get("children") or [])

        walk(data["parsed_structure"]["nodes"])

    doc.add_paragraph(
        f"合计：拆分前 {total_before} 条 -> 拆分后 {total_after} 条（涉及 {len(DEEP_SPLIT)} 个节点）"
    )
    doc.save(SHEET_PATH)
    print(f"确认单: {SHEET_PATH}")
    print(f"提案JSON: {PROPOSAL_PATH}")
    print(f"拆分前 {total_before} 条 -> 拆分后 {total_after} 条")


# ---------------------------------------------------------------------------
def api(base: str, method: str, path: str, token: str, payload: dict | None = None) -> dict:
    url = f"{base}/api{path}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def login(base: str, username: str, password: str) -> str:
    return api(base, "POST", "/auth/login", "", {"username": username, "password": password})["access_token"]


def apply_proposal(base: str, scheme_id: int, username: str, password: str) -> None:
    proposal = json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))
    token = login(base, username, password)
    tpl = api(base, "GET", f"/scheme-types/{scheme_id}/template", token)
    structure = tpl["parsed_structure"]
    if isinstance(structure, str):
        structure = json.loads(structure)

    touched: list[str] = []

    def walk(nodes: list) -> None:
        for n in nodes:
            tid = str(n.get("id") or "")
            if tid in proposal:
                n["check_items"] = [
                    {"id": it["id"], "text": it["text"]} for it in proposal[tid]["items"]
                ]
                touched.append(tid)
            walk(n.get("children") or [])

    walk(structure.get("nodes", []))
    if not touched:
        print("没有匹配到任何节点（提案里的节点 ID 与模板不一致？）")
        return
    api(
        base,
        "PUT",
        f"/scheme-types/{scheme_id}/template/structure",
        token,
        {"parsed_structure": structure},
    )
    print(f"已写入 check_items：{', '.join(touched)}")
    print("注意：模板 updated_at 已变化，缓存将按新指纹重新审核（预期行为）。")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", action="store_true", help="生成确认单与提案 JSON")
    ap.add_argument("--apply", action="store_true", help="把提案 JSON 应用到模板")
    ap.add_argument("--base", default="http://localhost:5173")
    ap.add_argument("--scheme-id", type=int, default=12)
    ap.add_argument("--username", default="admin")
    ap.add_argument("--password", default="admin1234")
    args = ap.parse_args()

    if args.sheet:
        build_sheet()
    elif args.apply:
        apply_proposal(args.base, args.scheme_id, args.username, args.password)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
