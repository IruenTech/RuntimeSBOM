# Spring Boot 3 `jar:nested:` PURL 핫픽스 (rc16)

첨부한 `sbom.json`에서 ASM 실행 추적은 정상(65,526회)이고 Maven PURL이 누락된 상태를 확인했습니다.

## 원인
`JarMetadata.resolve()`가 `jar:nested:/.../!BOOT-INF/lib/...jar!/`를 `file:` URI로 변환하지 못하여 `unknown`/`filename-only`로 되돌아갔습니다.

## GitHub 저장소 적용 (Windows PowerShell)

```powershell
cd 'D:\roykim\Documents\TestProject\RuntimeSBOM-Agent-Git'
$zip = "$HOME\Downloads\RuntimeSBOM-Phase25-SpringBoot3-PURL-Hotfix.zip"
Expand-Archive -LiteralPath $zip -DestinationPath (Get-Location).Path -Force
git status --short
git add src/main/java/com/iruen/runtimesbom/JarMetadata.java src/test/java/com/iruen/runtimesbom/Phase26SpringBoot3MetadataTest.java integration/fixture-src/integration/Phase26Boot3Smoke.java scripts/phase26-springboot3-metadata-test.sh scripts/phase26-boot3-agent-smoke.sh .github/workflows/phase25-official-asm.yml docs/PHASE26-BOOT3-NESTED-FIX.md results/phase26/hotfix-evidence.json
git commit -m "Fix Spring Boot 3 nested JAR Maven provenance"
git push origin main
```

`git status`에서 기존 작업 변경이 있을 경우 커밋 전에 검토하세요. 위 ZIP은 저장소 상대경로를 그대로 사용합니다.

## 테스트

- Maven 없이 `sh scripts/phase26-springboot3-metadata-test.sh`
- JDK 21 내장 ASM으로 `sh scripts/verify-jdk-asm.sh` 후 `sh scripts/phase26-boot3-agent-smoke.sh jdk-internal`
- GitHub Actions에서 **Phase25 official ASM build diagnostics and staging (never auto-deploy)** 재실행. 공식 ASM Agent 빌드 후 신규 테스트가 실행됩니다.

## 예상 정상 결과
`commons-lang3` 구성요소의 `name`, `version`, `purl`, `SHA-256` 및 `METHOD_EXECUTED`가 함께 나옵니다. 새로운 실제 호출 횟수는 매번 다를 수 있습니다.

이번 로컬 테스트는 JDK 21 내장 ASM 방식으로 수행되었으며, 사용자의 GitHub Actions 재실행 결과는 아직 없습니다. 운영 승인 HOLD.
