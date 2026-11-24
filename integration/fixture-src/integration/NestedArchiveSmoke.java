package integration;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.InputStream;
import java.net.URL;
import java.nio.file.Files;
import java.security.CodeSource;
import java.security.ProtectionDomain;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipInputStream;

/** Simulates a container-defined class with an outer-archive nested JAR CodeSource. */
public final class NestedArchiveSmoke {
  static byte[] read(InputStream input) throws Exception {
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    byte[] buf = new byte[4096]; int n;
    while ((n=input.read(buf))!=-1) out.write(buf,0,n);
    return out.toByteArray();
  }
  static final class Loader extends ClassLoader {
    final byte[] clazz;
    final ProtectionDomain pd;
    Loader(byte[] clazz, URL source) {
      super(NestedArchiveSmoke.class.getClassLoader());
      this.clazz=clazz;
      this.pd=new ProtectionDomain(new CodeSource(source,(java.security.cert.Certificate[])null),null,this,null);
    }
    @Override protected Class<?> loadClass(String name,boolean resolve)throws ClassNotFoundException {
      synchronized(getClassLoadingLock(name)) {
        Class<?> c=findLoadedClass(name);
        if(c==null && name.equals("fixture.lib.Helper")) c=defineClass(name,clazz,0,clazz.length,pd);
        if(c==null) c=super.loadClass(name,false);
        if(resolve) resolveClass(c);
        return c;
      }
    }
  }
  public static void main(String[] args) throws Exception {
    if(args.length!=3) throw new IllegalArgumentException("archive file, nested path, expected number");
    File archive=new File(args[0]).getCanonicalFile();
    byte[] jarBytes;
    try(ZipFile zip=new ZipFile(archive)){jarBytes=read(zip.getInputStream(zip.getEntry(args[1])));}
    byte[] classBytes=null;
    try(ZipInputStream zip=new ZipInputStream(new java.io.ByteArrayInputStream(jarBytes))) {
      ZipEntry e;
      while((e=zip.getNextEntry())!=null) if(e.getName().equals("fixture/lib/Helper.class")){classBytes=read(zip);break;}
    }
    if(classBytes==null)throw new IllegalStateException("fixture class missing");
    String source=archive.toURI().toURL().toExternalForm()+"!/"+args[1]+"!/";
    Loader loader=new Loader(classBytes,new URL(source));
    Class<?> type=Class.forName("fixture.lib.Helper",true,loader);
    Object obj=type.getConstructor().newInstance();
    int count=Integer.parseInt(args[2]);int checksum=0;
    for(int i=0;i<count;i++) checksum+=((Integer)type.getMethod("compute",int.class).invoke(obj,i));
    if(checksum!=3*count*(count-1)/2+count)throw new AssertionError("unexpected output");
    System.out.println("NESTED_ARCHIVE_PASS calls="+count+" checksum="+checksum);
  }
}
