# RuntimeSBOM Agent Phase28 — Operational-Readiness Tests

기반: Phase27 실제 CI 업로드 공식 ASM 9.7.1 Shaded JAR (`v1.0.0-rc16`). **Agent 자체는 이번 단계에서 재빌드/수정하지 않았습니다.** 운영 검증 도구를 추가했습니다.

## 신규 파일

- `scripts/phase28-performance.py` — 독립 JVM에서 baseline / loaded-only / asm-traced 반복 HTTP 성능 비교, CPU·RSS·GC 시도 및 SBOM 호출 확인
- `scripts/phase28-resilience.py` — 실제 공식 Agent + Collector의 장애, 디스크 큐 복구, JVM 재시작, 중복 수신 검증
- `scripts/phase28-local-gate.py` — 새 단위 테스트 + 복구 시험 + 3조건 성능 시험을 한 번에 실행
- `tests/test_phase28_validation.py` — 성능 집계 및 바이너리 정체성 테스트
- `.github/workflows/phase28-operational-validation.yml` — 기존 Phase26 성공 실행의 **동일 바이너리 아티팩트**를 내려받아 수동 실행 (자동 배포 없음)
- `docs/PHASE28-ENTERPRISE-OPERATIONS.md` — 현장 스테이징 실행 및 상용 WAS·AIX 체크리스트

## 실행

JDK 21 + javac + Python 3 + Linux/macOS (프로세스 메트릭은 Linux 전용):

```bash
python3 scripts/phase28-local-gate.py --quick
python3 scripts/phase28-local-gate.py
python3 scripts/phase28-performance.py --warmup 10 --duration 60 --repeats 3 --concurrency 8
```

기본 게이트는 모드별 5초 × 3회입니다. `--quick`은 개발 확인용입니다. 장시간의 실제 WAS 시험은 아직 수행하지 않았습니다.

결과: `results/phase28/` 의 JSON, JVM 로그, HTTP 메트릭.

## 출시 판정

**LOCAL VALIDATION PASS**인 경우에도 **PRODUCTION HOLD**입니다. 이 테스트는 스테이징의 실제 Spring Boot/Tomcat/JEUS/WebLogic/AIX 및 24시간 장시간 시험을 대체하지 않습니다. 성능 수치는 합성 부하이며 실제 성능 효과를 주장하지 않습니다.

## 현재 턴에서 실제 수행한 검증 (2026-11-26, UTC)

- `python3 scripts/phase28-local-gate.py --quick`: **3/3 PASS**. 전체 기본 게이트(3회 반복·5초)는 이 컨테이너의 실행 제한으로 완료되지 않았으므로 PASS로 표시하지 않습니다.
- `python3 scripts/phase28-performance.py --warmup 0.7 --duration 2 --repeats 2 --concurrency 4`: **PASS**. Baseline 4,065.53 TPS, Loading 3,945.34 TPS, ASM 4,025.32 TPS(각 중앙값, 짧은 2초 시험); ASM의 baseline 대비 TPS 변화 -0.99%, P95 +1.36%. 결코 상용 WAS 오버헤드 추정치가 아닙니다.
- `python3 scripts/phase28-resilience.py`: **PASS**. Collector 중단 1건 큐 보존, 재기동 후 2건 성공 저장, 중복 전송 200 확인·중복 스냅샷 0건.
- Collector Python regression: **14개 중 12개 PASS, 2개 SKIP**.
- 이전 27단계 공식 바이너리 회귀: **4/4 PASS** (공식 SHA·중첩 JAR/ WAR·HTTP).
- 운영 승인: **HOLD**. 장시간 WAS 운영 부하 / JEUS·WebLogic·AIX 미검증.

결과 원시 파일은 `results/phase28/performance-repeat2.json`, `results/phase28/resilience.json`, `results/phase28/local-gate.json`, `results/phase28/collector-unittest.log`에 포함되어 있습니다.
