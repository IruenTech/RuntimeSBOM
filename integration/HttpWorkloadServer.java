package integration;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import example.Worker;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicLong;

/** Test-only HTTP fixture, NOT Tomcat or Spring Boot. */
public final class HttpWorkloadServer {
    public static void main(String[] args) throws Exception {
        final int port = Integer.parseInt(args.length > 0 ? args[0] : "18771");
        final Worker worker = new Worker();
        final AtomicLong completed = new AtomicLong();
        final HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 64);
        server.createContext("/health", e -> respond(e, 200, "ok"));
        server.createContext("/work", e -> {
            if (!"GET".equals(e.getRequestMethod())) { respond(e, 405, "GET required"); return; }
            int checksum = 0;
            for (int j = 0; j < 40; j++) checksum += worker.compute(j);
            completed.incrementAndGet();
            respond(e, 200, "checksum=" + checksum);
        });
        server.createContext("/stats", e -> respond(e, 200, "completed=" + completed.get()));
        server.setExecutor(Executors.newFixedThreadPool(12));
        server.start();
        System.out.println("HTTP_FIXTURE_READY=" + port);
        System.out.flush();
        Runtime.getRuntime().addShutdownHook(new Thread(() -> server.stop(0)));
    }
    private static void respond(HttpExchange e, int status, String data) throws IOException {
        byte[] bytes = data.getBytes(StandardCharsets.UTF_8);
        e.getResponseHeaders().set("Content-Type", "text/plain; charset=utf-8");
        e.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = e.getResponseBody()) { out.write(bytes); }
    }
}
