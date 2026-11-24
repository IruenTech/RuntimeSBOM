package example;
/** A verification target for instrumented entry points and exception control flow. */
public final class InstrumentationSmoke {
  public static void main(String[] args) {
    Worker worker = new Worker();
    int checksum = 0;
    for (int i = 0; i < 12; i++) checksum += worker.compute(i);
    if (checksum != 168) throw new AssertionError("checksum=" + checksum);
    System.out.println("INSTRUMENTATION_SMOKE_PASS checksum=" + checksum);
  }
}
