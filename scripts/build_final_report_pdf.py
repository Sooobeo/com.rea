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
) -> Paragraph:
    style = ParagraphStyle(
        "CellTmp",
        parent=styles["KSmall" if small else "KBody"],
        fontName="MalgunBold" if bold else "Malgun",
        textColor=text_color,
        alignment=TA_LEFT,
    )
    return Paragraph(str(text), style)


def table(rows: list[list[str]], widths: list[float], header: bool = True, font_size: float = 7.5) -> Table:
    cooked = []
    for r_idx, row in enumerate(rows):
        is_header = header and r_idx == 0
        cooked.append(
            [cell(v, bold=is_header, text_color=colors.white if is_header else INK) for v in row]
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
        p("수주 → 매출 → 이익 → 현금 전환의 증거 상태", "CoverSub"),
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
        p("현재 결론: <b>운영 회복 확인 / 현금 전환 미완료 / 계약별 수익인식 U / 목표가격 U</b>", "KSub"),
        PageBreak(),
    ]

    story += [
        p("1. 분석 방법과 증거 규칙", "KHeading"),
        p("F는 공식 사실, C는 맥락, E는 공시 수치의 계산, M은 다음 확인 사건, U는 공개 증거로 식별 불가능한 값이다. 완료란 모든 칸을 숫자로 채우는 것이 아니라 확인 가능한 값은 수치로, 확인 불가능한 값은 근거 있는 U 판정으로 닫는 것이다."),
        figure(
            "05_v01_demand_to_revenue_evidence_path.png",
            "결론: 산업 수요와 엑시콘 매출 사이에는 고객 투자, 발주, 납품, 검수·수락이라는 별도의 증거 관문이 있다.",
            102,
        ),
        Spacer(1, 4 * mm),
        p("U를 0으로 바꾸거나 임의의 인식률·제품마진·Peer 배수를 넣지 않았다. 계약금액과 기납품은 확인되더라도 회사 전체 매출과 합산하지 않는다.", "KSmall"),
        PageBreak(),
    ]

    story += [
        p("2. 산업과 테스트 밸류체인", "KHeading"),
        p("엑시콘은 공시상 Memory Tester, SSD Tester, SoC Tester와 관련 보드·인터페이스 제품을 공급하는 후공정 테스트 장비 업체다. AI·HPC와 고용량 메모리 수요가 테스트 강도를 높일 수 있다는 설명은 맥락 C이며, 이를 엑시콘 점유율이나 계약금액으로 직접 치환하지 않는다."),
        figure(
            "05_v02_test_value_chain_position.png",
            "결론: 공식 제품군은 여러 테스트 기능 영역에 위치하지만 공시만으로 공정별 점유율이나 고객 투자 전환율은 알 수 없다.",
            105,
        ),
        Spacer(1, 4 * mm),
        p("웨이퍼 테스트와 패키지 최종 테스트를 분리해 표시했다. 이 도식은 시간 순서도가 아니라 공시상 제품 용도 영역의 지도다.", "KSmall"),
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
        p("2026년 상반기에는 실제 회사 전체 매출 412.74억원과 영업이익 21.69억원으로 운영 회복이 관측됐다. 다만 어떤 계약금액이 매출에 귀속됐는지는 식별되지 않고, 기납품 172.03억원을 상반기 매출에 다시 더할 수 없다."),
        p("분석의 초점은 수주 존재에서 검수·수락·매출·현금 전환으로 이동한다. 가장 강한 긍정 증거는 2분기 영업흑자이고, 가장 강한 경고 증거는 재고·채권 증가와 음의 OCF다. 동일 기준 Peer 배수가 없어 적정가치·목표가격 판단은 유보한다."),
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
        subject="2026년 수주·매출·현금 전환의 근거 기반 분석",
    )
    doc.build(build_story(), onFirstPage=page_decor, onLaterPages=page_decor)
    print(OUTPUT)


if __name__ == "__main__":
    main()
