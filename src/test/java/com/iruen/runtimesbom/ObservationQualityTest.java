package com.iruen.runtimesbom;

/** Java 8-compatible executable assertion suite; no JUnit dependencies. */
public final class ObservationQualityTest {
  private static void eq(String actual, String expected) {
    if (!expected.equals(actual)) throw new AssertionError(expected + " != " + actual);
  }
  private static void check(boolean value, String msg) { if (!value) throw new AssertionError(msg); }
  public static void main(String[] args) {
    ObservationQuality.Result loading=ObservationQuality.assess(false,false,0,1,0,0,0,0,0,0);
    eq(loading.level,"LOADING_ONLY");
    ObservationQuality.Result observed=ObservationQuality.assess(true,false,12,1,0,0,0,0,0,0);
    eq(observed.level,"OBSERVED_PARTIAL");
    check(observed.reasons.contains("OBSERVED_DOES_NOT_PROVE_COMPLETE"),"must not claim complete");
    eq(ObservationQuality.assess(true,false,0,1,0,0,0,0,0,0).level,"NO_METHOD_HITS");
    eq(ObservationQuality.assess(true,false,1,100,0,0,0,0,0,0).level,"SAMPLED");
    ObservationQuality.Result partial=ObservationQuality.assess(true,false,9,1,1,1,3,2,8,2);
    eq(partial.level,"DEGRADED");
    check(partial.reasons.contains("ISOLATED_CLASSLOADERS"),"missing loader loss reason");
    check(partial.reasons.contains("UNATTRIBUTED_ENTRIES"),"missing unattributed reason");
    eq(ObservationQuality.assess(true,true,2,1,0,0,0,0,0,0).level,"DEGRADED");
    System.out.println("PASS observation quality 6 scenarios");
  }
}
