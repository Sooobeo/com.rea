# 엑시콘 Phase 5 시각화 검증 보고서

## 1. 검증 범위와 최종 판정

- 대상 latest run: `20260831T133214+0900`
- 생성 시각: `2026-08-31T10:01:50+09:00`
- 프로젝트 컷오프: `2026-08-31T09:50:32+09:00`
- 최신성 gate: `raw/dart/phase3/gates/20260831T095032+0900/gate_summary.json`
- 최신성 gate run: `20260831T095032+0900`
- 최신성 gate에서 확인된 반기보고서 수: `1`
- 반영 범위: 2026년 반기보고서(`2026 H1`, 접수번호 `20260814001521`)의 2026Q2 손익 3개월 직접 공시 `F`, H1 누계−Q1 누계로 산출한 Q2 OCF `E`, 2026-06-30 재무상태, 2026-08-28 시장가치
- 최종 판정: 데이터, 자동 렌더, 수동 시각 검증이 모두 통과했으며 미해결 시각 결함은 `0건`이다.

| 검증 계층 | 결과 | 근거 |
|---|---:|---|
| Phase 5 데이터 검사 | **132/132 통과** | `raw/dart/normalized/phase5/runs/20260831T133214+0900/phase5_checks.json` |
| 자동 렌더 검사 | **77/77 통과** | `raw/dart/normalized/phase5/runs/20260831T133214+0900/phase5_render_manifest.json` |
| 수동 시각 QA | **11/11 통과** | `raw/dart/normalized/phase5/runs/20260831T133214+0900/phase5_manual_visual_qa.json` |
| 최종 PNG | **11개 생성 확인** | `figures/05_v01_*.png` ~ `figures/05_v11_*.png` |

## 2. 2026 H1 반영 확인

2026 H1은 단순 문구 갱신이 아니라 각 시각화의 입력과 결론에 반영됐다. 대표적으로 별도 제품매출 412.74억원 중 Memory Tester가 376.00억원(91.1%)을 차지했고, 연결 2026Q2 매출 314.69억원·영업이익 41.35억원은 R17 3개월 열에서 직접 확인한 F, OPM 13.14%는 E다. 같은 분기 말 재고는 464.94억원, 매출채권·기타유동채권은 151.18억원이며 독립 분기 OCF -30.73억원만 H1 누계−Q1 누계로 산출한 E다. 따라서 손익 흑자 전환과 현금 전환 미확인을 동시에 유지하는 것이 최신 결론이다.

최신성 판단은 gate `20260831T095032+0900`에 고정하며, 그 이후 공시는 이 보고서에 자동 포함된 것으로 간주하지 않는다. `U`는 실패나 0이 아니라 공식 증거 미확인을 뜻한다.

## 3. V1~V11 질문·결론·근거·파일

| ID | 검증 질문 | 결론 | 주요 근거·주의 | 시각화 파일 |
|---|---|---|---|---|
| V1 | AI·HPC 테스트 수요가 엑시콘 연결 매출로 곧바로 이어지는가? | 아니다; 고객 투자, 계약, 제작·납품, 검수·수락과 회계 인식 게이트를 통과해야 한다. | R01~R07, R11~R13, R17; 산업 맥락은 회사 실적이 아니며 계약 종료일·납품·지급조건도 수락 증거가 아니다. F/C/U/F-U 상태코드와 실선·점선 의미를 범례로 분리했다. | [figures/05_v01_demand_to_revenue_evidence_path.png](figures/05_v01_demand_to_revenue_evidence_path.png) |
| V2 | 엑시콘 제품은 어느 테스트 영역에 있고 도식이 잘못된 단일 공정 순서를 암시하는가? | 공시상 전기검사·신뢰성·에이징 영역에 있으나 도식은 비순차 기능영역이며, 웨이퍼 테스트는 패키징 전이고 패키지·최종 테스트는 패키징 후일 수 있다. | R01, R02와 회사 제품 용도 설명; 순차 화살표를 제거했으며 위치는 시장점유율이나 경쟁우위를 뜻하지 않는다. | [figures/05_v02_test_value_chain_position.png](figures/05_v02_test_value_chain_position.png) |
| V3 | 별도 기준 제품매출 구성은 2026 H1에 어떻게 바뀌었는가? | 2026 H1 별도 제품매출 412.74억원 중 Memory Tester가 376.00억원(91.1%)으로 중심이고 SSD Tester는 36.74억원(8.9%)이다. SoC 비중 0.0%는 F, 원문 공란과 총계 대사로 산출한 금액 0원은 E다. | R01, R02, R17 및 2024FY·2025Q1 제품표; OFS 제품 구성과 CFS 시계열을 합치지 않으며 0·미미값도 라벨에서 숨기지 않는다. | [figures/05_v03_product_mix_ofs.png](figures/05_v03_product_mix_ofs.png) |
| V4 | 2026Q2 흑자 전환을 정상 마진으로 볼 수 있는가? | 2026Q2 매출 314.69억원·영업이익 41.35억원·OPM 13.14%로 흑자 전환했지만 반복 관측이 부족해 정상 마진으로 고정할 수 없다. | OpenDART CFS; Q2 손익은 R17 3개월 열 직접 공시 F이고 OPM은 E다. Q2 OCF만 H1−Q1 계산 E이며, 매출·영업이익 패널과 OPM 패널을 분리해 twin-y의 이중 영점 오해를 제거했다. | [figures/05_v04_quarterly_revenue_opm_cfs.png](figures/05_v04_quarterly_revenue_opm_cfs.png) |
| V5 | 손익 회복이 현금 전환 회복까지 의미하는가? | 아니다; 2026Q2 재고 464.94억원과 채권 151.18억원이 늘었고 독립 분기 OCF는 -30.73억원으로 음수다. | R01, R02 및 과거 CFS; 재고·채권은 기말 stock이고 OCF는 분기 flow이므로 동행만으로 특정 계약 지연의 인과를 주장하지 않는다. | [figures/05_v05_working_capital_ocf_cfs.png](figures/05_v05_working_capital_ocf_cfs.png) |
| V6 | 공시 계약기간이나 기납품액으로 계약별 매출 인식 시점을 정할 수 있는가? | 아니다; 2026 수주표의 기납품액 172.03억원은 사실이지만 다섯 계약의 검수·고객 수락·인식 금액과 기간은 모두 U다. | R03~R07, R17, P2025-CORR-01 및 R01·R02·R17 수익인식 정책; 막대는 계약기간만 나타낸다. R04+R07의 최초 종료일 `2026-07-31`은 X와 날짜로 표시한다. | [figures/05_v06_contract_timeline_recognition_U.png](figures/05_v06_contract_timeline_recognition_U.png) |
| V7 | 2026 H1 실제 매출과 신규 계약가치를 더해 2026FY 매출을 만들 수 있는가? | 아니다; 2026 H1 실제 매출 412.74억원과 2026 신규 계약가치 1,018.02억원은 독립 레인이며 계약별 인식 귀속이 없어 2026FY는 U다. | R01~R07, R17 및 Phase 4 조건부 모델; 세 레인은 waterfall이 아니고 서로 가산하거나 순차 흐름으로 연결하지 않는다. | [figures/05_v07_actual_contract_recognition_bridge.png](figures/05_v07_actual_contract_recognition_bridge.png) |
| V8 | 현재 기준·상방·하방 시나리오는 어느 상태인가? | 현재는 중립색의 미해결 상태이고 기준·상방은 증거 대기, 하방은 일정 정정과 재고·채권·음수 OCF에 따른 부분 경고다. | R01~R07, R17 및 사건 상태 모델; 확률과 숫자형 사례 결과를 임의로 부여하지 않는다. | [figures/05_v08_evidence_scenario_state.png](figures/05_v08_evidence_scenario_state.png) |
| V9 | 공식 계약가치만으로 영업이익을 추정할 수 있는가? | 아니다; 관측 전사 OPM이 -20.05%에서 23.71%까지 달라 같은 계약가치의 기계적 손익 방향도 크게 바뀐다. | R01~R07 및 과거 CFS 마진; 계약가치 전액×전사 OPM은 독립 반사실 민감도일 뿐 예측·제품마진·인식률·확률이 아니다. 셀을 가리던 중앙 워터마크는 제거했고 우상단 비가림 경고 배지만 유지했다. | [figures/05_v09_counterfactual_contract_opm.png](figures/05_v09_counterfactual_contract_opm.png) |
| V10 | 현재 EV에서 요구 매출·이익과 목표가격을 방어적으로 역산할 수 있는가? | 시점 혼합 추정 EV 3,203.66억원은 계산되지만 동일 기준 Peer 배수가 없어 요구 매출·이익과 목표가격은 U다. | R09, R17; 시가총액 3,380.16억원에서 순현금 176.49억원을 차감했다. 렌더러는 날짜를 하드코딩하지 않고 `market_date=2026-08-28`, `balance_sheet_date=2026-06-30`을 동적으로 읽으며 자기진단 EV/LTM Sales 3.28배는 적정가치가 아니다. | [figures/05_v10_market_value_expectation_gate.png](figures/05_v10_market_value_expectation_gate.png) |
| V11 | 다음 공시에서 무엇이 상태를 바꾸는가? | 계약 규모보다 계약별 검수·수락·인식액, 재고·채권 전환, OCF 회복과 동일 기준 Peer 입력을 먼저 확인해야 한다. | R01~R17 및 최신 OpenDART gate; 확인·경고·U의 3상태만 사용하고 U를 0으로 대체하지 않는다. | [figures/05_v11_risk_monitoring_matrix.png](figures/05_v11_risk_monitoring_matrix.png) |

## 4. 최종 렌더러 패치 확인

- V9: 기존 중앙 대형 워터마크가 민감도 셀과 숫자를 가리던 문제를 제거했다. 최종 코드는 중앙 오버레이를 만들지 않으며, 축 상단 우측에 작은 `COUNTERFACTUAL · NOT FORECAST` 경고 배지만 둔다.
- V10: 시가총액일과 재무상태일을 문자열로 하드코딩하지 않는다. `valuation["market_date"]`와 `valuation["balance_sheet_date"]`를 읽어 최신 run의 `2026-08-28`, `2026-06-30`을 표시한다.
- 공통: 푸터 자동 줄바꿈과 안전여백, 고정 캔버스 저장을 적용했다. 자동 렌더 77개 검사는 11개 차트 각각의 폭·높이·용량·A4 core font·A4 source font·텍스트 clipping·텍스트 overlap 7개 항목으로 구성되며 모두 통과했고, 수동 시각 QA도 11/11 통과했다.

## 5. 재현 경로

- 차트 데이터: `raw/dart/normalized/phase5/runs/20260831T133214+0900/phase5_chart_data.json`
- 데이터 검사: `raw/dart/normalized/phase5/runs/20260831T133214+0900/phase5_checks.json`
- 실행 manifest: `raw/dart/normalized/phase5/runs/20260831T133214+0900/phase5_run_manifest.json`
- 렌더 manifest: `raw/dart/normalized/phase5/runs/20260831T133214+0900/phase5_render_manifest.json`
- 수동 시각 QA: `raw/dart/normalized/phase5/runs/20260831T133214+0900/phase5_manual_visual_qa.json`
- 렌더러: `scripts/render_phase5_chartpack.py`
- 재현 의존성: `requirements-chartpack.txt`
