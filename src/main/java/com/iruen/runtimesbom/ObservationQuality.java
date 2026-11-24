package com.iruen.runtimesbom;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Diagnostic observability assessment, NOT proof of complete runtime coverage.
 * A successful method hit proves that entry was observed; an absent hit never proves
 * that a method was never executed (sampling/late attachment/isolated loaders/etc).
 */
final class ObservationQuality {
  static final String LOADING_ONLY = "LOADING_ONLY";
  static final String DEGRADED = "DEGRADED";
  static final String SAMPLED = "SAMPLED";
  static final String NO_METHOD_HITS = "NO_METHOD_HITS";
  static final String OBSERVED_PARTIAL = "OBSERVED_PARTIAL";

  static final class Result {
    final String level;
    final List<String> reasons;
    Result(String level, List<String> reasons) {
      this.level = level;
      this.reasons = Collections.unmodifiableList(new ArrayList<String>(reasons));
    }
    String reasonCodes() { return String.join(";", reasons); }
  }
  private ObservationQuality() {}

  static Result assess(boolean tracingRequested, boolean tracingDisabled, long executedEntries,
                       int sampling, long transformErrors, long isolatedLoaders,
                       long registrationDrops, long eventDrops, long unattributedEntries,
                       int invalidEventKeys) {
    List<String> reasons = new ArrayList<String>();
    if (!tracingRequested) return new Result(LOADING_ONLY, Collections.singletonList("TRACE_NOT_REQUESTED"));
    if (tracingDisabled) reasons.add("TRACE_DISABLED");
    if (transformErrors > 0) reasons.add("TRANSFORM_FAILURES");
    if (isolatedLoaders > 0) reasons.add("ISOLATED_CLASSLOADERS");
    if (registrationDrops > 0) reasons.add("REGISTRATION_DROPS");
    if (eventDrops > 0) reasons.add("EVENT_DROPS");
    if (unattributedEntries > 0) reasons.add("UNATTRIBUTED_ENTRIES");
    if (invalidEventKeys > 0) reasons.add("INVALID_EVENT_KEYS");
    if (sampling > 1) reasons.add("SAMPLED_METHOD_EVENTS");
    if (executedEntries == 0) reasons.add("NO_OBSERVED_METHOD_ENTRIES");
    // For unavailable evidence, report the stronger failure mode first.
    for (String reason : reasons) {
      if (!"SAMPLED_METHOD_EVENTS".equals(reason) && !"NO_OBSERVED_METHOD_ENTRIES".equals(reason))
        return new Result(DEGRADED, reasons);
    }
    if (sampling > 1) return new Result(SAMPLED, reasons);
    if (executedEntries == 0) return new Result(NO_METHOD_HITS, reasons);
    return new Result(OBSERVED_PARTIAL, Collections.singletonList("OBSERVED_DOES_NOT_PROVE_COMPLETE"));
  }
}
