# Phase30 Tomcat 9 `NMT_METASPACE_UNAVAILABLE` 진단/호환성 패치

## 원인 범위
- 원본 `scripts/phase30-tomcat-retention.py`는 `jcmd PID VM.native_memory summary scale=KB` 출력에서 `- Metaspace (reserved=..., committed=...KB)` 패턴만 읽었습니다.
- Tomcat 9 CI는 JDK 11을 사용하며, JDK 11 NMT 출력은 `- Class (...)` 아래의 `(  Metadata: )` 다음 줄에 `committed=...KB`를 기록할 수 있습니다. 원본 정규식은 이 형식을 읽지 못합니다.
- **사용자가 업로드한 오류 로그만으로는 실제 NMT 결과의 형태가 확인되지 않습니다.** NMT가 비활성화된 JVM도 같은 `NMT_METASPACE_UNAVAILABLE` 판정이 가능합니다. 실패한 GitHub Actions 아티팩트의 `nmt-01.txt`를 보면 구분할 수 있습니다.

## 수정 범위
- **수정 파일:** `scripts/phase30-tomcat-retention.py`, `tests/test_phase30_stability.py`
- JVM 버전별 NMT 출력 두 형태 파싱:
  - `NMT_METASPACE_CATEGORY`: top-level `Metaspace (... committed=...KB)`
  - `NMT_CLASS_METADATA`: `Class` 내 `( Metadata: )` 바로 아래 `committed=...KB`
- `Class` 전체 committed 메모리나 `Class space` 값을 Metaspace로 오인하지 않습니다.
- JVM별로 실제로 사용한 `metaspaceMetricSource`를 각 `snapshots[]`에 기록합니다. 한 프로세스의 측정 도중 출처가 바뀌면 `HOLD`로 처리합니다.
- `Native memory tracking is not enabled`면 `NMT_DISABLED_CHECK_CATALINA_OPTS`, 형식 미인식이면 `NMT_FORMAT_UNRECOGNIZED_INSPECT_NMT_TXT`도 추가하여 **실패를 감추지 않습니다**.
- 모든 주기에서 `PHASE30_NMT_SAMPLE app=... cycle=... committedKiB=... source=...` 출력.
- 기존 보고서의 `metaspaceCommittedKiB`, SHA 검증, ClassLoader GC 검증 및 운영 `HOLD` 정책은 유지합니다.
- JDK11 `Metadata`와 JDK17 `Metaspace`는 엄밀하게 동일한 메모리 집계가 아닐 수 있습니다. 증가량은 같은 JVM의 동일 계측 출처 내에서만 비교하며 **서로 다른 JDK의 절대값을 직접 비교하지 않습니다**.

## 적용 (Windows PowerShell)
```powershell
cd D:\roykim\Documents\TestProject\RuntimeSBOM-Agent-Git
git status
Expand-Archive -LiteralPath "$HOME\Downloads\RuntimeSBOM-Phase30-NMT-Hotfix.zip" -DestinationPath . -Force
python -m unittest discover -s tests -p "test_phase30_stability.py" -v
git diff --stat
git add scripts/phase30-tomcat-retention.py tests/test_phase30_stability.py README-PHASE30-NMT-HOTFIX-KO.md
git commit -m "Fix Phase30 Tomcat9 JDK11 NMT metadata parsing"
git push origin main
```

GitHub Actions > `Phase30 exact ASM Tomcat classloader GC and Metaspace staging (manual, no deploy)` 수동 재실행. 기존에 검증된 **같은** Phase26 Agent/Phase29 성공 실행 ID를 입력하십시오. *이번 패치는 Agent 바이너리를 변경하지 않습니다.*

## 실패 시 어떤 파일을 볼까?
GitHub Actions Artifacts에서 `phase30-tomcat9-retention` 다운로드 후:
- `nmt-01.txt`: `Native memory tracking is not enabled`인지 또는 `Metadata:`/`Metaspace`가 있는지
- `retention.json`: `snapshots[].metaspaceMetricSource` 및 `failures`
- `tomcat-server.log`: JVM 기동/계측 오류 여부

`nmt-01.txt`에 `Native memory tracking is not enabled`라고 나오면 출력 파싱 수정만으로 해결되지 않습니다. Tomcat 기동 스크립트의 `CATALINA_OPTS`에 `-XX:NativeMemoryTracking=summary`가 실제로 전달되는지 확인해야 합니다. NMT는 이미 기동된 JVM에서 활성화할 수 없습니다.

## 확인 범위
- JDK 11/JDK 21 형식의 문자열 픽스처 및 실패 시나리오 단위 테스트
- 해당 환경에서 사용 가능한 JDK 21 `jcmd` 실측 출력 파서 검사
- Tomcat 9 + JDK 11 실제 GitHub Actions 재실행은 **미완료**
- 운영 배포는 계속 **HOLD**
