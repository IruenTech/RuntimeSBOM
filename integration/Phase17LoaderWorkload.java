import java.io.File;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;

/** Simulates two independent application loaders and a parent-isolated deployment. */
public final class Phase17LoaderWorkload {
  private static int invoke(URL archive, ClassLoader parent, int times) throws Exception {
    try (URLClassLoader loader = new URLClassLoader(new URL[]{archive}, parent)) {
      Class<?> type = Class.forName("fixture.lib.Helper", true, loader);
      Object instance = type.newInstance();
      Method compute = type.getMethod("compute", int.class);
      int sum = 0;
      for (int i = 0; i < times; i++) {
        int out = ((Integer) compute.invoke(instance, i)).intValue();
        if (out != i * 3 + 1) throw new AssertionError("Incorrect fixture result");
        sum++;
      }
      return sum;
    }
  }
  public static void main(String[] args) throws Exception {
    if (args.length != 1) throw new IllegalArgumentException("expected one fixture JAR path");
    URL jar = new File(args[0]).toURI().toURL();
    int appA = invoke(jar, ClassLoader.getSystemClassLoader(), 3);
    int appB = invoke(jar, ClassLoader.getSystemClassLoader(), 5);
    // A parent-isolated loader has no access to the agent's Recorder bridge.
    // Its library can still be listed as CLASS_LOADED, not METHOD_EXECUTED.
    int isolated = invoke(jar, null, 7);
    if (appA != 3 || appB != 5 || isolated != 7) throw new AssertionError("incorrect calls");
    System.out.println("PASS enterprise classloader fixture: delegated=3+5 isolated=7");
  }
}
