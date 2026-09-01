from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


REPO = Path(__file__).resolve().parents[1]
OUTPUT = REPO / "output" / "pdf" / "03_엑시콘_기업분석_보고서.pdf"
FIGURES = REPO / "figures"

NAVY = colors.HexColor("#183B63")
BLUE = colors.HexColor("#2E6F9E")
TEAL = colors.HexColor("#168B78")
AMBER = colors.HexColor("#E39A20")
RED = colors.HexColor("#C8574D")
INK = colors.HexColor("#20242B")
MUTED = colors.HexColor("#697586")
GRID = colors.HexColor("#D8DEE8")
LIGHT = colors.HexColor("#F3F5F8")
PALE_BLUE = colors.HexColor("#E8F1F8")
PALE_AMBER = colors.HexColor("#FFF1D5")


def register_fonts() -> None:
    pdfmetrics.registerFont(TTFont("Malgun", r"C:\Windows\Fonts\malgun.ttf"))
    pdfmetrics.registerFont(TTFont("MalgunBold", r"C:\Windows\Fonts\malgunbd.ttf"))
    pdfmetrics.registerFontFamily("Malgun", normal="Malgun", bold="MalgunBold")


register_fonts()
styles = getSampleStyleSheet()
styles.add(
    ParagraphStyle(
        name="KTitle",
        parent=styles["Title"],
        fontName="MalgunBold",
        fontSize=25,
        leading=34,
        textColor=INK,
        spaceAfter=12,
        wordWrap="CJK",
    )
)
styles.add(
    ParagraphStyle(
        name="KHeading",
        parent=styles["Heading1"],
        fontName="MalgunBold",
        fontSize=17,
        leading=23,
        textColor=NAVY,
        spaceAfter=9,
        wordWrap="CJK",
    )
)
styles.add(
    ParagraphStyle(
        name="KSub",
        parent=styles["Heading2"],
        fontName="MalgunBold",
        fontSize=11.5,
        leading=16,
        textColor=BLUE,
        spaceBefore=5,
        spaceAfter=5,
        wordWrap="CJK",
    )
)
styles.add(
    ParagraphStyle(
        name="KBody",
        parent=styles["BodyText"],
        fontName="Malgun",
        fontSize=9.2,
        leading=14.2,
        textColor=INK,
        spaceAfter=7,
        wordWrap="CJK",
    )
)
styles.add(
    ParagraphStyle(
        name="KSmall",
        parent=styles["BodyText"],
        fontName="Malgun",
        fontSize=7.7,
        leading=11.2,
        textColor=MUTED,
        wordWrap="CJK",
    )
)
styles.add(
    ParagraphStyle(
        name="KCaption",
        parent=styles["BodyText"],
        fontName="Malgun",
        fontSize=8.2,
        leading=12,
        textColor=RED,
        alignment=TA_LEFT,
        spaceBefore=4,
        wordWrap="CJK",
    )
)
styles.add(
    ParagraphStyle(
        name="CoverTitle",
        parent=styles["Title"],
        fontName="MalgunBold",
        fontSize=31,
        leading=42,
        textColor=colors.white,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )
)
styles.add(
    ParagraphStyle(
        name="CoverSub",
        parent=styles["BodyText"],
        fontName="Malgun",
        fontSize=12.5,
        leading=20,
        textColor=colors.HexColor("#D9E8F4"),
        wordWrap="CJK",
    )
)


def p(text: str, style: str = "KBody") -> Paragraph:
    return Paragraph(text, styles[style])


def cell(
    text: str,
    bold: bool = False,
    small: bool = True,
    text_color=INK,
    font_size: float | None = None,
    leading: float | None = None,
) -> Paragraph:
    parent = styles["KSmall" if small else "KBody"]
    style = ParagraphStyle(
        "CellTmp",
        parent=parent,
        fontName="MalgunBold" if bold else "Malgun",
        textColor=text_color,
        alignment=TA_LEFT,
        fontSize=font_size or parent.fontSize,
        leading=leading or (font_size + 3 if font_size else parent.leading),
    )
    return Paragraph(str(text), style)


def table(rows: list[list[str]], widths: list[float], header: bool = True, font_size: float = 7.5) -> Table:
    cooked = []
    for r_idx, row in enumerate(rows):
        is_header = header and r_idx == 0
        cooked.append(
            [
                cell(
                    v,
                    bold=is_header,
                    text_color=colors.white if is_header else INK,
                    font_size=font_size,
                    leading=font_size + 3,
                )
                for v in row
            ]
        )
    t = Table(cooked, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("FONTNAME", (0, 0), (-1, -1), "Malgun"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, GRID),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "MalgunBold"),
        ]
    for r_idx in range(1 if header else 0, len(rows)):
        if r_idx % 2 == 0:
            commands.append(("BACKGROUND", (0, r_idx), (-1, r_idx), LIGHT))
    t.setStyle(TableStyle(commands))
    return t


def figure(name: str, caption: str, max_height_mm: float = 94) -> KeepTogether:
    path = FIGURES / name
    from PIL import Image as PILImage

    with PILImage.open(path) as img:
        width_px, height_px = img.size
    target_width = 186 * mm
    target_height = target_width * height_px / width_px
    max_height = max_height_mm * mm
    if target_height > max_height:
        scale = max_height / target_height
        target_width *= scale
        target_height *= scale
    return KeepTogether(
        [
            Image(str(path), width=target_width, height=target_height, hAlign="CENTER"),
            p(caption, "KCaption"),
        ]
    )


def bullet(text: str) -> Paragraph:
    style = ParagraphStyle(
        "BulletTmp",
        parent=styles["KBody"],
        leftIndent=11,
        firstLineIndent=-8,
        bulletIndent=0,
    )
    return Paragraph(f"• {text}", style)


def page_decor(canvas, doc) -> None:
    canvas.saveState()
    width, height = A4
    if doc.page == 1:
        canvas.setFillColor(NAVY)
        canvas.rect(0, 0, width, height, fill=1, stroke=0)
        canvas.setFillColor(TEAL)
        canvas.rect(0, 0, width, 13 * mm, fill=1, stroke=0)
    else:
        canvas.setStrokeColor(GRID)
        canvas.line(12 * mm, height - 15 * mm, width - 12 * mm, height - 15 * mm)
        canvas.setFont("Malgun", 7.2)
        canvas.setFillColor(MUTED)
        canvas.drawString(12 * mm, height - 11.5 * mm, "엑시콘 기업분석 | 공시 2026-08-31 · 시장 2026-08-28 · 재무 2026-06-30")
        canvas.line(12 * mm, 13 * mm, width - 12 * mm, 13 * mm)
        canvas.drawString(12 * mm, 8.5 * mm, "근거 우선 F/C/E/M/U · 목표가격 미산출")
        canvas.drawRightString(width - 12 * mm, 8.5 * mm, f"{doc.page}")
    canvas.restoreState()


def build_story() -> list:
    story: list = []

    story += [
        Spacer(1, 48 * mm),
        p("엑시콘 기업분석 보고서", "CoverTitle"),
        Spacer(1, 7 * mm),
        p("산업구조 → 엑시콘 포지션 → 수주·매출·현금 전환", "CoverSub"),
        Spacer(1, 45 * mm),
        p("분석 기준", "CoverSub"),
        p("공시 컷오프 2026-08-31 09:50 KST", "CoverSub"),
        p("시장가격 2026-08-28 종가 · 재무 2026-06-30", "CoverSub"),
        Spacer(1, 22 * mm),
        p("서술형 기업분석 · 적정가치/목표주가/투자의견 미제시", "CoverSub"),
        PageBreak(),
    ]

    story += [
        p("Executive Summary", "KHeading"),
        p("2026년 상반기에는 매출과 영업이익의 전환이 확인됐지만 현금 전환은 아직 끝나지 않았다. 연결 매출 412.74억원, 영업이익 21.69억원, OCF -83.11억원이다. 2분기 OPM은 13.14%로 회복했으나 파생 OCF는 -30.73억원이다."),
        p("산업 배경은 우호적이다. SEMI는 2026년 글로벌 테스트 장비 매출이 31.0% 증가한 153억달러에 이를 것으로 전망했고 AI·HBM·이종 패키징의 복잡성과 성능·신뢰성 요구를 동인으로 제시했다. 그러나 이는 산업 맥락 C이지 엑시콘 매출 성장률이 아니다."),
        p("엑시콘의 확인된 위치는 후공정 Memory·Burn-in·CLT, SSD Aging Tester와 관련 Board, CIS 중심 SoC Tester다. 2026 H1 제품매출은 Memory 91.1%, SSD 8.9%, SoC 비중 0.0%였다. 전용 HBM Tester와 HBM 직접 매출은 U다."),
        p("반기보고서 수주표의 계약가치 1,018.01억원과 기납품 172.03억원은 사실이다. 그러나 표에는 재무상태표일 뒤인 7월 7일 계약 498.50억원이 포함되고, 계약별 검수·고객수락·연결매출 귀속액은 없다. 계약가치·기납품은 F, 계약별 수익인식액은 U다."),
        p("8월 28일 종가 25,900원 기준 시가총액은 3,380.16억원, 6월 말 순현금을 차감한 시점 혼합 추정 EV는 3,203.66억원이다. EV/LTM Sales 3.28배는 현재가격 자기진단일 뿐 적정가치가 아니다."),
        Spacer(1, 3 * mm),
        table(
            [
                ["핵심 질문", "현재 답", "상태"],
                ["계약이 2026년 매출로 얼마나 인식됐는가", "계약별 식별 불가", "U"],
                ["이익과 현금으로 전환됐는가", "H1 EBIT 21.69 / OCF -83.11억원", "F/E"],
                ["현재 시장가치는 무엇을 반영하는가", "EV 3,203.66억원 · 3.28x Sales", "E"],
                ["숫자형 Base·목표주가를 낼 수 있는가", "동일 기준 Peer·인식액 부재", "U"],
                ["다음 결론 변경 조건", "검수·수락·Q3 현금전환·정정공시", "M"],
            ],
            [76 * mm, 78 * mm, 22 * mm],
        ),
        Spacer(1, 5 * mm),
        p("현재 결론: <b>산업 순풍 C / Memory·SSD 포지션 확인 / 운영 회복 F / 현금 전환 미완료 / 계약별 수익인식 U</b>", "KSub"),
        PageBreak(),
    ]

    story += [
        p("1. 분석 방법과 업종 범위", "KHeading"),
        p("F는 공식 사실, C는 산업·회사 맥락, E는 공시 수치의 계산, M은 다음 확인 사건, U는 공개 증거로 식별 불가능한 값이다. 확인 가능한 값은 수치로, 확인 불가능한 값은 근거 있는 U로 닫는다."),
        table(
            [
                ["업종 범주", "기능", "대표 구성", "엑시콘과의 관계"],
                ["ATE", "전기 신호로 기능·성능·신뢰성 판정", "Tester·Test Head·Software", "핵심 사업 범주"],
                ["Interface·이송·열제어", "소자 접촉·자동 이송·온도 제어", "Board·Socket·Probe Card·Handler·Chamber", "일부 Board·Chamber형 장비"],
                ["검사·계측", "물리 결함·치수 측정", "광학·전자빔 검사장비", "전기적 테스트와 다른 장비군"],
                ["OSAT", "패키징·테스트 위탁 제조", "Assembly·Package Test Service", "서비스 사업자가 아닌 장비 공급사"],
            ],
            [31 * mm, 52 * mm, 50 * mm, 43 * mm],
            font_size=7.0,
        ),
        Spacer(1, 6 * mm),
        p("읽을 때의 핵심", "KSub"),
        bullet("글로벌 Test Equipment 전망은 엑시콘의 Addressable Opportunity를 설명하는 C이며 회사 매출 전망이 아니다."),
        bullet("계약가치·기납품·회사 전체 매출·계약별 수익인식은 서로 다른 증거 레인이다."),
        bullet("U를 0으로 바꾸거나 임의의 인식률·제품마진·Peer 배수를 넣지 않는다."),
        PageBreak(),
    ]

    story += [
        p("2.1 산업구조와 테스트 경제성", "KHeading"),
        p("반도체 테스트는 제조가 끝난 뒤 한 번 수행하는 단일 공정이 아니다. 설계 검증에서 웨이퍼, 패키지 Final Test, Burn-in, System Level Test와 SSD Aging까지 여러 삽입점에서 품질·수율·출시속도·테스트 원가를 관리한다."),
        table(
            [
                ["단계", "주요 주체", "테스트 셀", "경제적 목적"],
                ["설계·평가", "Fabless·IDM", "ATE·Device Interface", "설계 결함 조기 발견·출시 단축"],
                ["웨이퍼 테스트", "Foundry·IDM·OSAT", "ATE·Prober·Probe Card", "불량 Die 선별·Known Good Die"],
                ["패키징", "IDM·OSAT", "2.5D/3D·Chiplet·HBM Integration", "기능 통합·대역폭·전력 효율"],
                ["Final·Burn-in·SLT", "IDM·OSAT", "ATE·Handler·Socket·Board·Thermal", "기능·신뢰성·Mission Mode 검증"],
                ["Module·Storage", "Memory·SSD 제조사", "Module·CLT·SSD Aging System", "완제품 안정성·Protocol·장시간 부하"],
            ],
            [30 * mm, 40 * mm, 57 * mm, 49 * mm],
            font_size=7.0,
        ),
        Spacer(1, 6 * mm),
        p("장비 수요의 방향", "KSub"),
        p("소자 수 × Test Insertion 수 × Test Time ÷ Parallelism - 기존 장비 재사용·업그레이드 = 신규 Tester·Board·Service 수요의 방향", "KBody"),
        table(
            [
                ["수요를 높이는 요인", "신규 장비를 상쇄하는 요인"],
                ["고속 I/O·전력밀도·Chiplet·3D 적층·HBM·고가 Package", "Parallel Test·Adaptive Test·수율 안정화"],
                ["성능·신뢰성 규격 강화·다중 Test Insertion·Thermal Control", "기존 Platform 재사용·Module Upgrade·Dual Sourcing"],
                ["신규 Protocol·대용량 SSD·짧은 제품 전환주기", "고객 Capex 시점 지연·검증 기간 장기화"],
            ],
            [88 * mm, 88 * mm],
            font_size=7.2,
        ),
        Spacer(1, 5 * mm),
        p("근거: R20 Advantest Investors Guide 2026. 양산 테스트는 Wafer Test와 Package Test로 구분되고, 고성능 소자일수록 Tester·Handler·Device Interface·열제어를 함께 최적화해야 한다.", "KSmall"),
        PageBreak(),
    ]

    story += [
        p("2.2 2026년 산업 동향", "KHeading"),
        p("AI/HPC는 Logic·HBM·Storage의 수요뿐 아니라 열·신호무결성·신뢰성 검증을 어렵게 해 테스트 강도를 높인다. 그러나 산업 전망과 글로벌 장비사 실적을 엑시콘 성장률로 대입하지 않는다."),
        table(
            [
                ["공식 근거", "확인된 변화", "엑시콘 해석", "상태·공백"],
                ["R18 SEMI 2026-07", "Test Equipment 2025 +55.3%, 2026 +31.0%·153억달러 전망", "글로벌 기회 집합 확대", "산업 C / 점유율 U"],
                ["R19 SEMI 2026-04", "AI Training-HBM, Inference-Data Center NAND·Storage", "Memory·SSD 방향성과 부합", "발주 전환 M/U"],
                ["R21 Advantest IAR", "Chiplet·2.5D/3D·HBM이 Thermal·Signal·Reliability 복잡도 확대", "테스트 난도 상승은 우호적", "HBM 직접 매출 U"],
                ["R22 Teradyne 10-K", "2025 AI Compute가 Test 성장을 견인; HBM·DRAM Final Test 중요", "실제 업계 사례", "타사 실적 대입 금지"],
            ],
            [31 * mm, 62 * mm, 48 * mm, 35 * mm],
            font_size=6.8,
        ),
        Spacer(1, 6 * mm),
        bullet("SEMI는 2026년 DRAM 장비 +39.0%, NAND 장비 +30.7%를 전망하고 한국 투자 동인으로 HBM 등 첨단 Memory를 제시했다."),
        bullet("Advanced Package는 더 많은 Test Insertion·Thermal·System-level 검증을 요구하지만 Exicon 전용 HBM Tester는 공개되지 않았다."),
        bullet("Enterprise SSD·NAND 확대는 SSD Aging Tester의 방향성과 맞지만 고객 투자·규격·수주·검수 전환은 별도 증거다."),
        p("결론: 업황 강세는 기회를 넓히지만 엑시콘의 고객 승인·수주·검수·현금 회수를 자동으로 보장하지 않는다.", "KCaption"),
        PageBreak(),
    ]

    story += [
        p("2.3 엑시콘의 포지션", "KHeading"),
        p("엑시콘은 AI Test 생태계 전체를 공급하는 Global Full-line ATE 기업도, 반복 교체형 Probe Card·Socket 순수업체도 아니다. 공시로 확인되는 중심은 후공정 Memory·Burn-in·CLT, SSD Aging Tester와 관련 Board이며 SoC·CIS는 확장 영역이다."),
        figure(
            "05_v02_test_value_chain_position.png",
            "결론: 제품군은 여러 테스트 기능 영역에 있지만 공정별 점유율·HBM 직접 매출·고객 투자 전환율은 U다.",
            76,
        ),
        Spacer(1, 3 * mm),
        table(
            [
                ["제품군", "기능 영역", "2026 H1", "산업 노출", "공백"],
                ["Memory·CLT·Burn-in·CIB", "DRAM Component·Module·Reliability", "91.1% F", "Advanced Memory C", "세부매출·HBM·점유율 U"],
                ["SSD Tester", "SATA·SAS·PCIe Gen5·UFS Aging", "8.9% F", "eSSD·NAND C", "고객·규격별 매출·Margin U"],
                ["SoC·CIS", "Wafer/Package 기능 Test Platform", "0.0% F / 금액 0 E", "AI ASIC·CIS C", "양산매출·점유율 U"],
                ["Board·Interface", "Memory 범주 내 CIB·Board", "별도 미공개", "설치기반 후속수요 C", "반복매출·교체주기 U/M"],
            ],
            [36 * mm, 50 * mm, 29 * mm, 31 * mm, 30 * mm],
            font_size=6.5,
        ),
        PageBreak(),
    ]

    story += [
        p("2.4 이 분석이 갖는 의미", "KHeading"),
        p("산업 호황은 기회 집합을 넓히지만 회사 수혜를 확정하지 않는다. 핵심은 산업 성장률을 낙관적으로 반복하는 것이 아니라 산업 수요가 실제 회사의 발주·매출·현금으로 전환되는지를 단계별 공식 증거로 확인하는 데 있다."),
        figure(
            "05_v01_demand_to_revenue_evidence_path.png",
            "결론: 산업 수요와 엑시콘 매출 사이에는 고객 투자, 발주, 납품, 검수·수락이라는 별도의 증거 관문이 있다.",
            94,
        ),
        Spacer(1, 4 * mm),
        table(
            [
                ["층위", "현재 확인", "상태", "분석 의미"],
                ["산업", "Test Equipment·Memory·Storage 투자 확대", "C", "기회 집합 확대"],
                ["회사", "대형 수주·H1 매출 회복·Q2 영업흑자", "F/E", "상업적 포착의 초기 증거"],
                ["실행", "계약별 검수·매출 귀속 U, OCF 음수", "U/M", "수혜 확정과 현금 전환은 미완료"],
                ["가치", "EV 계산 가능, 동일 Peer·목표가격 U", "E/U", "산업 강세만으로 적정가치 결론 금지"],
            ],
            [26 * mm, 70 * mm, 22 * mm, 58 * mm],
            font_size=7.0,
        ),
        PageBreak(),
    ]

    story += [
        p("3. 회사와 제품 구조", "KHeading"),
        p("2026년 상반기 별도(OFS) 제품 매출은 Memory 376.00억원(91.1%), SSD 36.74억원(8.9%), SoC 0에 가까운 수준이다. Memory에는 Burn-in, CLT, CIB Board 등이 포함돼 있어 임의 분해하지 않았다. CFS 총매출과 원 단위로 일치하지만 제품 믹스는 OFS 공시다."),
        figure(
            "05_v03_product_mix_ofs.png",
            "결론: 상반기 매출 회복은 Memory 계열에 집중돼 있고 SoC·서비스의 별도 양산매출 증거는 아직 없다.",
            103,
        ),
        Spacer(1, 4 * mm),
        p("주요 고객 1의 상반기 매출은 395.96억원, 연결 총매출의 95.93%다. 공개된 2026년 계약 4건의 상대방도 모두 삼성전자다.", "KSub"),
        PageBreak(),
    ]

    story += [
        p("4. Historical 실적과 재무 품질", "KHeading"),
        table(
            [
                ["구분", "매출(억원)", "GP(억원)", "EBIT(억원)", "NI(억원)", "OCF(억원)", "OPM"],
                ["2025 H1", "94.83", "12.94", "-85.87", "-32.84", "-104.26", "-90.55%"],
                ["2026 Q1", "98.06", "34.06", "-19.66", "9.35", "-52.38", "-20.05%"],
                ["2026 Q2", "314.69", "111.55", "41.35", "75.87", "-30.73 E", "13.14%"],
                ["2026 H1", "412.74", "145.61", "21.69", "85.21", "-83.11", "5.26%"],
            ],
            [26 * mm, 24 * mm, 23 * mm, 23 * mm, 23 * mm, 25 * mm, 25 * mm],
        ),
        Spacer(1, 4 * mm),
        figure(
            "05_v04_quarterly_revenue_opm_cfs.png",
            "결론: 2분기에는 영업레버리지로 흑자 전환했지만 과거 분기 편차가 커 단일 분기 마진을 장기화할 수 없다.",
            120,
        ),
        p("Q2 매출·GP·EBIT·NI는 R17의 3개월 열 직접 공시 F이며, Q2 OCF만 H1 누계−Q1 누계로 산출한 E다.", "KSmall"),
        p("상반기 순이익에는 지분법이익 37.97억원, 관계기업처분익 9.28억원, 법인세수익 7.96억원이 포함된다. 순이익률을 정상 영업수익성으로 쓰지 않았다.", "KSmall"),
        PageBreak(),
    ]

    story += [
        p("5. 운전자본과 현금 전환", "KHeading"),
        p("재고는 2025년 말 289.47억원에서 2026년 1분기 374.61억원, 6월 말 464.94억원으로 증가했다. 6월 말 유동 채권은 151.18억원으로 1분기보다 112.78억원 늘었다. 상반기 OCF는 -83.11억원이었다."),
        figure(
            "05_v05_working_capital_ocf_cfs.png",
            "결론: 매출과 영업이익이 회복된 2분기에도 재고·채권 증가와 음의 OCF가 함께 나타나 현금 전환 검증이 남아 있다.",
            120,
        ),
        Spacer(1, 4 * mm),
        p("현금 358.99억원과 단기금융상품 50억원에서 차입금 232.50억원을 차감한 계산상 순현금은 176.49억원이다. 유동성 위기로 단정할 근거는 없으나 제작·납품·회수 사이의 운전자본 부담은 실제다.", "KSmall"),
        PageBreak(),
    ]

    story += [
        p("6. 수주 원장과 인식 공백", "KHeading"),
        table(
            [
                ["ID", "계약", "가치(억원)", "기납품(억원)", "잔고(억원)", "종료일", "인식"],
                ["R03", "CLT·SSD", "302.00", "160.00", "142.00", "2026-12-31", "U"],
                ["R04+R07", "Interface Board", "96.86", "12.03", "84.83", "2026-09-04", "U"],
                ["R05", "CIB 등", "120.65", "0.00", "120.65", "2026-12-31", "U"],
                ["R06", "CLT·SSD", "498.50", "0.00", "498.50", "2026-12-31", "U"],
            ],
            [18 * mm, 36 * mm, 21 * mm, 21 * mm, 21 * mm, 36 * mm, 19 * mm],
        ),
        Spacer(1, 3 * mm),
        figure(
            "05_v06_contract_timeline_recognition_U.png",
            "결론: 종료일과 기납품 사실은 확인되지만 계약별 검수·수락·수익인식 시점은 여전히 공백이다.",
            110,
        ),
        p("공시 수주표 합계 1,018.01억원·기납품 172.03억원·잔고 845.98억원에는 7월 7일 계약 498.50억원이 포함된다. 845.98억원을 6월 30일 잔고로 표시하지 않는다.", "KSmall"),
        PageBreak(),
    ]

    story += [
        p("7. 비가산 증거 레인", "KHeading"),
        p("반기보고서는 R03·R04에 대해 판매·공급과 현금수령 약 160억원·12억원을 보여준다. 하지만 계약별 검수·고객 수락·연결매출 귀속 문구는 없다. 회사 전체 실제 매출, 공식 계약가치, 계약별 인식증거는 독립 레인이다."),
        figure(
            "05_v07_actual_contract_recognition_bridge.png",
            "결론: 회사 전체 매출, 계약가치, 계약별 인식증거는 어떤 두 숫자도 더할 수 없는 독립 증거다.",
            105,
        ),
        Spacer(1, 4 * mm),
        p("기납품 172.03억원을 2026 H1 매출 412.74억원에 더하지 않는다. R03 혼합계약의 기납품을 Memory와 SSD에 배분하지 않는다.", "KSub"),
        PageBreak(),
    ]

    story += [
        p("8. 조건부 시나리오", "KHeading"),
        p("상반기까지는 실제치로 닫았고 하반기 숫자형 Base·Bull·Bear는 만들지 않았다. 시나리오는 공식 증거가 들어올 때 상태가 바뀌는 사건 규칙이다."),
        table(
            [
                ["상태", "진입 조건", "조치"],
                ["Base 대기", "계약 유지 + 공식 검수·수락·인식액", "확인액만 H2 bridge에 연결"],
                ["Bull 대기", "추가 계약·신규제품 매출 + 현금전환", "공식 금액과 실제 마진만 추가"],
                ["Bear 부분 경고", "연장·감액·해지 또는 재고·채권·OCF 악화", "영향 계약 U/이연/제거"],
            ],
            [35 * mm, 77 * mm, 64 * mm],
        ),
        Spacer(1, 4 * mm),
        figure(
            "05_v08_evidence_scenario_state.png",
            "결론: 현재 Base와 Bull은 증거 대기이고 일정과 현금전환에는 부분 경고가 켜져 있다.",
            92,
        ),
        PageBreak(),
    ]

    story += [
        p("9. 반사실 손익 범위 검사", "KHeading"),
        p("아래 표는 공식 계약가치 전액에 과거 연결 OPM을 곱한 기계 계산이다. 인식률·제품마진·확률·가이던스가 아니다."),
        figure(
            "05_v09_counterfactual_contract_opm.png",
            "결론: 수주 규모보다 실제 인식 시점과 전사 마진 상태가 손익 방향을 좌우하므로 계약액 단독 전망은 무효다.",
            105,
        ),
        Spacer(1, 4 * mm),
        p("498.5억원 계약도 OPM -20.05%에서는 약 -100억원, OPM 23.71%에서는 약 +118억원의 산술 결과가 된다. 2026Q2 OPM 13.14%와 2026Q1 -20.05%를 모두 관측 범위로 보존했다.", "KSmall"),
        PageBreak(),
    ]

    story += [
        p("10. 시장가치와 내재 기대", "KHeading"),
        table(
            [
                ["항목", "값", "기준"],
                ["종가", "25,900원", "2026-08-28 F"],
                ["시가총액", "3,380.16억원", "13,050,797주 사용 E"],
                ["순현금", "176.49억원", "2026-06-30 E"],
                ["시점 혼합 추정 EV", "3,203.66억원", "E"],
                ["EV/LTM Sales · EBIT", "3.28배 · 29.57배", "자기진단"],
                ["요구 실적·목표가격", "산출 불가", "Peer 배수 U"],
            ],
            [59 * mm, 58 * mm, 59 * mm],
        ),
        Spacer(1, 3 * mm),
        figure(
            "05_v10_market_value_expectation_gate.png",
            "결론: EV는 계산할 수 있으나 동일 기준 Peer 배수가 없어 요구 실적과 목표가격은 U다.",
            110,
        ),
        p("가격일 8월 28일과 재무일 6월 30일이 다르다. EV/LTM Sales 3.28배는 적정가치나 목표배수가 아니다.", "KSmall"),
        PageBreak(),
    ]

    story += [
        p("11. 리스크와 업데이트 모니터링", "KHeading"),
        bullet("고객 집중: 주요 고객 1 매출 비중 95.93%, 공개 계약 4건의 상대방 동일."),
        bullet("인식·납기: R04 일정 연장 이력, R03·R05·R06 종료일 12월 31일 집중."),
        bullet("현금 전환: 재고·채권 증가와 H1·Q2 음의 OCF."),
        bullet("제품 집중: OFS Memory 91.1%; SoC·CXL·서비스 양산매출 U."),
        bullet("감사 판단: 2026년 감사인 변경, 확보한 본문 XML에 반기검토 결론 없음."),
        bullet("K-IFRS 1118: 2027년 적용 시 영업손익 정의 bridge 필요."),
        figure(
            "05_v11_risk_monitoring_matrix.png",
            "결론: 다음 공시에서 계약 규모보다 검수·인식, 재고·채권 정상화, OCF 회복을 먼저 확인해야 한다.",
            125,
        ),
        PageBreak(),
    ]

    story += [
        p("12. 결론과 재현성", "KHeading"),
        p("산업 측면에서는 AI/HPC, Advanced Memory, NAND·Enterprise SSD, Advanced Packaging이 테스트 삽입 수·난도·신뢰성 요구를 높이는 순풍이 확인된다. 다만 엑시콘의 현재 실적 포지션은 Memory·SSD 중심이고 HBM 직접 매출·SoC 양산매출·공정별 점유율은 U다."),
        p("2026년 상반기에는 실제 회사 전체 매출 412.74억원과 영업이익 21.69억원으로 운영 회복이 관측됐다. 다만 어떤 계약금액이 매출에 귀속됐는지는 식별되지 않고, 기납품 172.03억원을 상반기 매출에 다시 더할 수 없다."),
        p("이 분석의 의미는 산업 수요 → 고객 투자 → 장비 승인·수주 → 납품·검수 → 매출 인식 → 현금 회수의 전환 사슬을 분리하는 데 있다. 가장 강한 긍정 증거는 2분기 영업흑자이고, 가장 강한 경고 증거는 재고·채권 증가와 음의 OCF다. 동일 기준 Peer 배수가 없어 적정가치·목표가격 판단은 유보한다."),
        p("최종 판정", "KSub"),
        table(
            [
                ["운영 회복", "현금 전환", "계약별 인식", "목표가격"],
                ["확인", "미완료", "U", "U"],
            ],
            [44 * mm] * 4,
        ),
        Spacer(1, 6 * mm),
        p("QA 결과", "KSub"),
        table(
            [
                ["계층", "결과"],
                ["OpenDART 정규화", "208/208 PASS"],
                ["Phase 3 Historical·계약", "47/47 PASS"],
                ["Phase 4 모델·시장가치", "138/138 PASS"],
                ["Phase 5 차트 데이터", "132/132 PASS"],
                ["Phase 5 렌더", "77/77 PASS"],
                ["수동 시각 QA", "11/11 PASS · 미해결 결함 0"],
            ],
            [87 * mm, 89 * mm],
        ),
        Spacer(1, 5 * mm),
        p("핵심 공식 원문", "KSub"),
        p("R17: <link href='https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814001521' color='#2E6F9E'>2026년 반기보고서</link> · R10: <link href='https://dart.fss.or.kr/navi/searchNavi.do?naviCode=A002&amp;naviCrpCik=00611736&amp;naviCrpNm=%EC%97%91%EC%8B%9C%EC%BD%98' color='#2E6F9E'>DART 정기공시 검색</link> · R09: <link href='https://kind.krx.co.kr/common/stockprices.do?isurCd=09287&amp;method=searchStockPricesMain' color='#2E6F9E'>KIND 주가정보</link>", "KSmall"),
        p("R18: <link href='https://www.semi.org/en/semi-press-release/global-semiconductor-equipment-sales-forecast-to-reach-a-record-229-billion-dollars-in-2028-semi-reports' color='#2E6F9E'>SEMI 2026 Mid-Year Equipment Forecast</link> · R19: <link href='https://www.semi.org/en/semi-press-release/semi-projects-double-digit-growth-in-global-300mm-fab-equipment-spending-for-2026-and-2027' color='#2E6F9E'>SEMI 300mm Fab Outlook</link>", "KSmall"),
        p("R20: <link href='https://www.advantest.com/document/en/investors/ir-library/investors-guide/Investors_Guide_2601E.pdf' color='#2E6F9E'>Advantest Investors Guide 2026</link> · R21: <link href='https://www.advantest.com/document/en/investors/ir-library/annual/E_all_IAR2025.pdf' color='#2E6F9E'>Advantest IAR 2025</link> · R22: <link href='https://investors.teradyne.com/sec-filings/all-sec-filings/content/0001193125-26-059002/ter-20251231.htm' color='#2E6F9E'>Teradyne 2025 Form 10-K</link>", "KSmall"),
        p("Phase 5 run 20260831T133214+0900<br/>H1 원문 SHA-256: 035C607AE99C700743F24DA5A84246D27A7E7D9A75BD9DC8BABD383AF65F7505", "KSmall"),
    ]
    return story


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
        title="엑시콘 기업분석 보고서",
        author="Codex",
        subject="반도체 테스트 산업구조·엑시콘 포지션·수주·매출·현금 전환 분석",
    )
    doc.build(build_story(), onFirstPage=page_decor, onLaterPages=page_decor)
    print(OUTPUT)


if __name__ == "__main__":
    main()
