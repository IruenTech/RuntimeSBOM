import java.io.File;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;

/** Multi-deployment synthetic test; NOT a real Tomcat / Spring Boot runtime. */
public final class Phase19ProvenanceWorkload {
  private static void run(String filename, ClassLoader parent, int count, int scale, int offset)
      throws Exception {
    URL jar=new File(filename).toURI().toURL();
    try(URLClassLoader cl=new URLClassLoader(new URL[]{jar},parent)) {
      Class<?> cls=Class.forName("fixture.lib.Helper",true,cl);
      Object helper=cls.newInstance();
      Method method=cls.getMethod("compute",int.class);
      for(int i=0;i<count;i++) {
        int result=((Integer)method.invoke(helper,i)).intValue();
        if(result!=i*scale+offset)throw new AssertionError("wrong class or library: "+result);
      }
    }
  }
  public static void main(String[] args) throws Exception {
    if(args.length!=2)throw new IllegalArgumentException("expected 2 JAR paths");
    run(args[0],ClassLoader.getSystemClassLoader(),3,3,1);
    run(args[1],ClassLoader.getSystemClassLoader(),4,5,2);
    run(args[1],null,5,5,2); // Cannot see the Agent Recorder, must not fabricate execution.
    run(args[0],ClassLoader.getSystemClassLoader(),2,3,1);
    System.out.println("PASS: 3+4+5+2 calls; observable 9, isolated 5");
  }
}
