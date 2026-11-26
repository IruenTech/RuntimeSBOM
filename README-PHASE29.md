# RuntimeSBOM Agent Phase29 — WAS lifecycle & sustained observation

이 단계는 **Phase28 프로젝트의 모든 소스 및 공식 rc16 Shaded ASM JAR을 유지**한 상태에서 새 테스트 도구를 추가합니다. Agent 자체는 변경하지 않았습니다.

## 추가된 것

| 경로 | 기능 |
|---|---|
| `scripts/phase29-sustained.py` | 동일 JVM에서 연속 HTTP 측정 창을 수집; CPU·RSS·GC·TPS·P95/P99 |
| `scripts/phase29-outage-replay.py` | Collector 장기 단절 축소 시험, 다중 JVM 영속 큐, 서버 재시작/멱등 재전송 |
| `scripts/phase29-was-lifecycle.py` | Boot2/3의 JVM 재시작과 Tomcat9/10의 WAR undeploy/redeploy 자동화 (CI 실제 실행 필요) |
| `scripts/phase29-local-gate.py` | 4그룹 단축 또는 기본 회귀 게이트 |
| `scripts/phase29-review-gate.py` | CI 증거 4 WAS + 로컬 4그룹 SHA·실행 증거 필수 확인; 누락 시 HOLD |
| `tests/test_phase29_validation.py` | 신규 단위·음성 테스트 10개 |
| `.github/workflows/phase29-was-lifecycle.yml` | 공식 Phase26 바이너리 Run ID로 실서버 검증 수동 실행 |
| `docs/PHASE29-LIFECYCLE-AND-SUSTAINED.md` | 현장 시나리오·승인 보류 기준 |

## 즉시 실행

JDK 21 + Python 3(Collector 표준 라이브러리) + Linux 환경:

```bash
python3 scripts/phase29-local-gate.py --quick
```

장시간 실행을 포함한 기본 게이트:

```bash
python3 scripts/phase29-local-gate.py
```

> 기본 게이트도 합성 스테이징 축소 검증입니다. 실제 WAS/24시간 성능 검증을 대체하지 않습니다.

**운영 승인: HOLD.** Maven/Tomcat 미설치 환경에서는 실서버 수명주기 시험 미실행. 자세한 명령은 `docs/PHASE29-LIFECYCLE-AND-SUSTAINED.md`를 참조하세요.
