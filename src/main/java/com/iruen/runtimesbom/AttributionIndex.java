package com.iruen.runtimesbom;

import java.util.*;

/** Snapshot-time correlation of instrumented entry events to exact source + loader.
 * Never infer a component match from a Maven coordinate or a class name alone.
 * Input maps are snapshots, not an audit-transaction boundary.
 */
final class AttributionIndex {
  static final class Summary {
    long entries;
    int distinctMethods;
  }
  final Map<String, Summary> byOrigin = new HashMap<String, Summary>();
  long unattributedEntries;
  int unattributedMethods;
  int invalidEvents;

  static AttributionIndex build(Map<String, Long> events, Map<String, String> overrides,
                                Set<String> observedOrigins) {
    AttributionIndex result = new AttributionIndex();
    for (Map.Entry<String, Long> e : events.entrySet()) {
      Long raw = e.getValue();
      if (raw == null || raw.longValue() <= 0L) continue;
      String event = e.getKey();
      int hash = event.indexOf('#');
      String classPart = hash < 0 ? "" : event.substring(0, hash);
      int marker = classPart.lastIndexOf("|loader=");
      int separator = marker < 0 ? -1 : classPart.indexOf('|', marker + 8);
      if (separator < 0 || separator <= marker + 8 || separator >= classPart.length() - 1
          || hash == event.length() - 1) {
        result.invalidEvents++;
        result.unattributedEntries += raw.longValue();
        result.unattributedMethods++;
        continue;
      }
      String origin = classPart.substring(0, separator);
      String redirect = overrides.get(classPart);
      if (redirect != null && !redirect.isEmpty())
        origin = redirect + "|loader=" + classPart.substring(marker + 8, separator);
      if (!observedOrigins.contains(origin)) {
        result.unattributedEntries += raw.longValue();
        result.unattributedMethods++;
        continue;
      }
      Summary s = result.byOrigin.get(origin);
      if (s == null) { s = new Summary(); result.byOrigin.put(origin, s); }
      s.entries += raw.longValue();
      s.distinctMethods++;
    }
    return result;
  }
}
