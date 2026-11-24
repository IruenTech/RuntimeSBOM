package com.iruen.runtimesbom;

import java.io.*;
import java.net.*;
import java.util.concurrent.atomic.AtomicLong;

/** Bounded collector transport. Network I/O never runs in an instrumented method. */
final class CollectorClient {
  private CollectorClient() {}

  static void post(File file, String endpoint, String tokenEnv, String assetId,
                   int timeoutMs, AtomicLong success, AtomicLong failures) {
    if (send(file, endpoint, tokenEnv, assetId, timeoutMs, null)) success.incrementAndGet();
    else failures.incrementAndGet();
  }

  /** true only when collector confirms 2xx; retryable HTTP statuses have bounded retries. */
  static boolean send(File file, String endpoint, String tokenEnv, String assetId,
                      int timeoutMs, String deliveryId) {
    try {
      URL u = new URL(endpoint);
      if (!"https".equalsIgnoreCase(u.getProtocol()) && !"http".equalsIgnoreCase(u.getProtocol()))
        throw new IOException("Only HTTP(S) supported");
      if ("http".equalsIgnoreCase(u.getProtocol()) &&
          !("127.0.0.1".equals(u.getHost()) || "localhost".equalsIgnoreCase(u.getHost())))
        throw new IOException("Remote HTTP disallowed; use HTTPS");
      if (!file.isFile() || file.length() < 2 || file.length() > 8L * 1024 * 1024)
        throw new IOException("Missing or oversized SBOM");
      if (deliveryId != null && !deliveryId.matches("[0-9a-f]{32}")) throw new IOException("Invalid delivery ID");
      int lastStatus = 0;
      for (int attempt = 1; attempt <= 3; attempt++) {
        HttpURLConnection c = null;
        try {
          c = (HttpURLConnection)u.openConnection();
          c.setConnectTimeout(timeoutMs);
          c.setReadTimeout(timeoutMs);
          c.setRequestMethod("POST");
          c.setDoOutput(true);
          c.setInstanceFollowRedirects(false);
          c.setRequestProperty("Content-Type", "application/vnd.cyclonedx+json; version=1.6");
          c.setRequestProperty("X-RuntimeSBOM-Asset", assetId);
          if (deliveryId != null) c.setRequestProperty("X-RuntimeSBOM-Delivery-ID", deliveryId);
          String token = System.getenv(tokenEnv);
          if (token != null && !token.isEmpty()) c.setRequestProperty("Authorization", "Bearer " + token);
          c.setFixedLengthStreamingMode((int)file.length());
          try (InputStream in = new FileInputStream(file); OutputStream out = c.getOutputStream()) {
            byte[] b = new byte[16384]; int n;
            while ((n = in.read(b)) != -1) out.write(b, 0, n);
          }
          lastStatus = c.getResponseCode();
          if (lastStatus >= 200 && lastStatus < 300) return true;
          if (!retryStatus(lastStatus)) break;
        } catch (IOException ex) {
          if (attempt == 3) throw ex;
        } finally { if (c != null) c.disconnect(); }
        if (attempt < 3) {
          try { Thread.sleep(100L * attempt); }
          catch (InterruptedException ie) { Thread.currentThread().interrupt(); break; }
        }
      }
      throw new IOException("collector status " + lastStatus);
    } catch (Exception ex) {
      System.err.println("[RuntimeSBOM] collector upload failed: " + ex.getClass().getSimpleName() + ": " + ex.getMessage());
      return false;
    }
  }

  private static boolean retryStatus(int status) {
    return status == 408 || status == 429 || status == 500 || status == 502 || status == 503 || status == 504;
  }
}
