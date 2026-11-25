package integration;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.IOException;
import java.net.URL;
import java.net.URLConnection;
import java.net.URLStreamHandler;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipInputStream;

/** Tests Spring Boot 3 CodeSource URL shape without requiring a Spring Boot runtime. */
public final class Phase26Boot3Smoke {
  public static void main(String[] args) throws Exception {
    if(args.length!=3)throw new IllegalArgumentException("outer archive, inner path, call count");
    File archive=new File(args[0]).getCanonicalFile();
    byte[] inner;
    try(ZipFile outer=new ZipFile(archive)){
      ZipEntry jar=outer.getEntry(args[1]);
      if(jar==null)throw new IllegalStateException("inner JAR missing");
      inner=NestedArchiveSmoke.read(outer.getInputStream(jar));
    }
    byte[] clazz=null;
    try(ZipInputStream nested=new ZipInputStream(new ByteArrayInputStream(inner))){
      ZipEntry e;
      while((e=nested.getNextEntry())!=null){
        if("fixture/lib/Helper.class".equals(e.getName())){
          clazz=NestedArchiveSmoke.read(nested);
          break;
        }
      }
    }
    if(clazz==null)throw new IllegalStateException("class missing");
    // This URL mimics the CodeSource URL produced by Spring Boot 3's launcher.
    String source="jar:nested:"+archive.toURI().getRawPath()+"/!"+args[1]+"!/";
    URL origin=new URL(null,source,new URLStreamHandler(){
      @Override protected URLConnection openConnection(URL url) throws IOException {
        throw new IOException("test source URL is a CodeSource identifier only");
      }
    });
    NestedArchiveSmoke.Loader loader=new NestedArchiveSmoke.Loader(clazz,origin);
    Class<?> clazzType=Class.forName("fixture.lib.Helper",true,loader);
    Object obj=clazzType.getConstructor().newInstance();
    int count=Integer.parseInt(args[2]);int checksum=0;
    for(int i=0;i<count;i++)checksum+=((Integer)clazzType.getMethod("compute",int.class).invoke(obj,i));
    if(checksum != 3*count*(count-1)/2+count)throw new AssertionError("bad checksum");
    System.out.println("NESTED_ARCHIVE_PASS calls="+count+" checksum="+checksum);
  }
}
