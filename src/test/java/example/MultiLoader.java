package example;
import java.net.*;
import java.io.*;
/** Loads two independent copies of the same library in child-first URLClassLoaders. */
public class MultiLoader {
  static class Child extends URLClassLoader {
    Child(URL jar){super(new URL[]{jar},ClassLoader.getSystemClassLoader());}
    @Override protected synchronized Class<?> loadClass(String name,boolean resolve)throws ClassNotFoundException{
      if(name.equals("example.Worker")){
        Class<?> c=findLoadedClass(name);if(c==null)c=findClass(name);if(resolve)resolveClass(c);return c;
      }return super.loadClass(name,resolve);
    }
  }
  public static void main(String[] args)throws Exception{
    URL jar=new File(args[0]).toURI().toURL();
    for(int i=0;i<2;i++)try(Child loader=new Child(jar)){
      Object worker=loader.loadClass("example.Worker").newInstance();
      int result=(Integer)worker.getClass().getMethod("compute",int.class).invoke(worker,2);
      if(result!=7)throw new AssertionError(result);
    }
  }
}
