import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import java.io.File;
import java.io.IOException;
import java.io.OutputStream;
import java.lang.reflect.Method;
import java.net.InetSocketAddress;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Phase21 local-only HTTP workload, NOT a real Spring Boot/Tomcat runtime.
 * The same Maven PURL is served from distinct physical JARs and loaders.
 * One HTTP work request causes 1 old, 2 new, 1 isolated method invocation.
 * 3 of 4 invocations can be seen by Recorder; isolated calls are NOT observed.
 */
public final class Phase21HttpProvenanceServer {
    private static final class LoadedHelper implements AutoCloseable {
        final URLClassLoader loader;
        final Object instance;
        final Method compute;
        LoadedHelper(String jar, ClassLoader parent) throws Exception {
            loader = new URLClassLoader(new URL[]{new File(jar).toURI().toURL()}, parent);
            Class<?> type = Class.forName("fixture.lib.Helper", true, loader);
            instance = type.newInstance();
            compute = type.getMethod("compute", int.class);
        }
        int invoke(int i) throws Exception { return ((Integer) compute.invoke(instance, i)).intValue(); }
        @Override public void close() throws IOException { loader.close(); }
    }
    private static void respond(HttpExchange ex, int status, String text) throws IOException {
        byte[] b = text.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", "text/plain; charset=utf-8");
        ex.sendResponseHeaders(status, b.length);
        try (OutputStream out = ex.getResponseBody()) { out.write(b); }
    }
    public static void main(String[] args) throws Exception {
        if (args.length != 3) throw new IllegalArgumentException("port oldJar newJar");
        final int port = Integer.parseInt(args[0]);
        if (port < 1024 || port > 65535) throw new IllegalArgumentException("invalid port");
        final LoadedHelper old = new LoadedHelper(args[1], ClassLoader.getSystemClassLoader());
        final LoadedHelper updated = new LoadedHelper(args[2], ClassLoader.getSystemClassLoader());
        final LoadedHelper isolated = new LoadedHelper(args[2], null);
        final AtomicInteger completed = new AtomicInteger();
        final AtomicInteger errors = new AtomicInteger();
        final HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 64);
        server.createContext("/health", new HttpHandler() {
            @Override public void handle(HttpExchange ex) throws IOException { respond(ex, 200, "ok"); }
        });
        server.createContext("/work", new HttpHandler() {
            @Override public void handle(HttpExchange ex) throws IOException {
                if (!"GET".equals(ex.getRequestMethod())) { respond(ex, 405, "GET only"); return; }
                try {
                    int result = old.invoke(1) + updated.invoke(1) + updated.invoke(1) + isolated.invoke(1);
                    if (result != 25) throw new AssertionError("unexpected compute result: " + result);
                    completed.incrementAndGet();
                    respond(ex, 200, "checksum=25");
                } catch (Throwable problem) {
                    errors.incrementAndGet();
                    respond(ex, 500, "execution error");
                }
            }
        });
        server.createContext("/stats", new HttpHandler() {
            @Override public void handle(HttpExchange ex) throws IOException {
                respond(ex, 200, "completed=" + completed.get() + ";errors=" + errors.get());
            }
        });
        server.setExecutor(Executors.newFixedThreadPool(8));
        Runtime.getRuntime().addShutdownHook(new Thread(new Runnable() {
            @Override public void run() {
                server.stop(0);
                try { old.close(); updated.close(); isolated.close(); } catch (IOException ignored) { }
            }
        }));
        server.start();
        System.out.println("PHASE21_HTTP_READY=" + port);
        System.out.flush();
    }
}
