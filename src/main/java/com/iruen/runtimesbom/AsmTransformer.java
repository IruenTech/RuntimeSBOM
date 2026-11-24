package com.iruen.runtimesbom;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

/** ASM 9 method-entry transformer. No redefinition; fail-open for every class. */
public final class AsmTransformer implements ClassFileTransformer {
  @Override public byte[] transform(ClassLoader loader, String name, Class<?> redef,
                                    ProtectionDomain domain, byte[] bytes) {
    if (name == null || bytes == null || redef != null || loader == null ||
        name.startsWith("com/iruen/runtimesbom/") || name.startsWith("java/") ||
        name.startsWith("javax/") || name.startsWith("sun/") ||
        name.startsWith("jdk/") || name.startsWith("org/objectweb/asm/") ||
        name.startsWith("com/iruen/shaded/asm/") || !matches(name) ||
        RuntimeSbomAgent.traceDisabled ||
        RuntimeSbomAgent.successfulTransforms.get()>=RuntimeSbomAgent.maxTransformedClasses ||
        RuntimeSbomAgent.transformFailures.get()>=RuntimeSbomAgent.maxTransformErrors) {
      if(RuntimeSbomAgent.transformFailures.get()>=RuntimeSbomAgent.maxTransformErrors)
        RuntimeSbomAgent.transformerDisabled.incrementAndGet();
      return null;
    }
    // Do not inject a Recorder call into a loader that cannot resolve the
    // IDENTICAL Agent Recorder class. Missing/child-first Recorder copies are skipped.
    if (!RuntimeSbomAgent.visibleFrom(loader)) {
      RuntimeSbomAgent.classLoaderIsolated.incrementAndGet();
      return null;
    }
    RuntimeSbomAgent.classLoaderVisible.incrementAndGet();
    final String source = RuntimeSbomAgent.source(domain);
    if (source.length() == 0 || source.equals(RuntimeSbomAgent.agentLocation)) return null;
    final String prefix = RuntimeSbomAgent.key(source, loader) + "|" + name.replace('/', '.');
    try {
      final int[] instrumented = {0};
      ClassReader reader = new ClassReader(bytes);
      ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);
      reader.accept(new ClassVisitor(Opcodes.ASM9, writer) {
        @Override public MethodVisitor visitMethod(int access, String method, String descriptor,
                                                     String signature, String[] exceptions) {
          MethodVisitor mv = super.visitMethod(access, method, descriptor, signature, exceptions);
          if (mv == null || (access & (Opcodes.ACC_ABSTRACT | Opcodes.ACC_NATIVE)) != 0 ||
              method.equals("<init>") || method.equals("<clinit>")) return mv;
          final String event = prefix + "#" + method + descriptor;
          final int eventId = RuntimeSbomAgent.registerEvent(event);
          if(eventId==0)return mv;
          return new MethodVisitor(Opcodes.ASM9, mv) {
            @Override public void visitCode() {
              super.visitCode();
              super.visitLdcInsn(Integer.valueOf(eventId));
              super.visitMethodInsn(Opcodes.INVOKESTATIC, "com/iruen/runtimesbom/Recorder",
                                    "hit", "(I)V", false);
              instrumented[0]++;
            }
          };
        }
      }, 0);
      if (instrumented[0] == 0) return null;
      byte[] transformed=writer.toByteArray();
      RuntimeSbomAgent.successfulTransforms.incrementAndGet();
      return transformed;
    } catch (Throwable failure) {
      RuntimeSbomAgent.skippedTransforms.incrementAndGet();
      RuntimeSbomAgent.transformFailures.incrementAndGet();
      return null;
    }
  }

  private static boolean matches(String className) {
    for (String pkg : RuntimeSbomAgent.tracedPackages)
      if (!pkg.isEmpty() && (className.equals(pkg) || className.startsWith(pkg + "/"))) return true;
    return false;
  }
}
