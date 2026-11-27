# RuntimeSBOM Agent — Phase30: Tomcat ClassLoader GC / Metaspace staging test

## 현재 확인된 근거 (업로드된 Phase29 Artifacts)

- 스테이징 검토: `ELIGIBLE_FOR_HUMAN_REVIEW`, 운영 배포: `HOLD`.
- 공식 Agent SHA-256 (보고서에 기록된 값): `f3bf7b98591e5838cbe52f70ef97e5b8184d021ba1297b1d35b4789067a466ed`.
- Spring Boot 2, Spring Boot 3, Tomcat 9/10이 모두 `PASS`; `commons-lang3:3.14.0`의 PURL·실행 증거·의존성 SHA가 일치.
- Tomcat 재배포 후 SBOM에서 이전/새 클래스 로더의 이력이 공존. 이는 **GC 이후의 살아 있는 객체**를 입증하거나 누수를 증명하지 않음.
- Collector 테스트의 실제 장애 시간 0.2초, 합성 부하 윈도우 1초 × 2회; 장시간 성능/장애 시험 증거 아님.
- 업로드된 6개 ZIP에는 새 공식 SHA의 **실제 Agent JAR 바이트**는 포함되지 않음. Phase30 실행 시 성공한 Phase26의 정확한 JAR을 다운로드하고 빌드·감사 기록을 대조해야 함.

## 패치 내용

- `.github/workflows/phase30-retention-staging.yml` — 수동 실행 전용, Tomcat 9(JDK 11)·10(JDK 17) 매트릭스, 운영 배포 작업 없음.
- `scripts/phase30-tomcat-retention.py` — 격리된 Catalina Base에 WAR를 6/12회 배포, HTTP 요청·PURL·실행 증거 확인. 각 회차 뒤 `jcmd GC.run`, `GC.class_histogram`, `VM.native_memory summary scale=KB`를 저장.
- `scripts/phase30-review-gate.py` — Phase29에 합격한 **정확히 같은** 공식 Agent SHA, 두 Tomcat 보고서, 실행 증거, GC 및 Metaspace 샘플이 있어야 사람의 검토 대상 `ELIGIBLE_FOR_HUMAN_REVIEW`로 분류. 운영 배포는 항상 HOLD.
- `scripts/phase30-evidence-audit.py` — 사용자 제공 Phase29 Artifact ZIP 6개를 오프라인으로 검사.
- `tests/test_phase30_stability.py` — 정상·오류 상황의 단위 테스트 12개.

### 필요 조건

- Phase29 Queue Race Hotfix를 포함한 정상 GitHub 저장소.
- **29단계에 사용한** 공식 Agent를 빌드한 Phase26의 성공 실행 ID. 이전 SHA `ed5613...`로 빌드된 실행 ID를 사용하면 **SHA 불일치로 실패**해야 정상.
- 현재 제공된 29단계 보고서의 Agent SHA `f3bf7b...`와 일치하는 Phase26 빌드 아티팩트가 GitHub Actions에 보존되어 있어야 함.
- `phase29-staging-review-report`가 있는 29단계 성공 실행 ID.

## Windows PowerShell 적용 방법

```powershell
cd D:\roykim\Documents\TestProject\RuntimeSBOM-Agent-Git
git status
Expand-Archive -LiteralPath "$HOME\Downloads\RuntimeSBOM-Phase30-Tomcat-Retention-Patch.zip" -DestinationPath . -Force
python -m unittest discover -s tests -p "test_phase30_*.py" -v
git diff --stat
git add -A
git commit -m "Add Phase30 Tomcat GC and Metaspace staging gate"
git push origin main
```

업로드만으로는 자동으로 실행되지 않습니다. GitHub Actions > **Phase30 exact ASM Tomcat classloader GC and Metaspace staging (manual, no deploy)** > Run workflow로 실행합니다.

- `phase26_run_id`: 반드시 SHA `f3bf7b...` Agent를 빌드한 Phase26 성공 실행 ID.
- `phase29_run_id`: 이번에 PASS한 Phase29의 실행 페이지 URL 맨 끝 숫자.
- `redeploy_cycles`: 기본 `6`; 필요시 `12`.

## 결과 다운로드

- `phase30-tomcat9-retention`: `retention.json`, `histogram-*.txt`, `nmt-*.txt`, `tomcat-sbom.json`, 서버 로그.
- `phase30-tomcat10-retention`: 위와 동일.
- `phase30-classloader-review`: 최종 배포 검토 결과 `review.json`.

`HOLD` 판정 시 설정을 완화해 통과시키지 말고, 해당 JCMD 원시 데이터와 WAS 로그를 확인하십시오. 이번 시험은 강제 GC 직후의 ClassLoader 도달 가능성에 대한 스테이징 관찰로, 장시간 누수 부재를 증명하지 않습니다. 실제 1~2시간 지속 부하·24시간 장애 복구 및 JEUS/WebLogic/AIX 검증은 별도 단계입니다.
