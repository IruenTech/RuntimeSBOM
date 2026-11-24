package com.iruen.runtimesbom;

import java.io.*;
import java.net.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.jar.*;
import java.util.zip.*;

/** Provenance resolver. Does not invent Maven versions from filenames. */
final class JarMetadata {
  final String group,name,version,sha256,confidence;
  private JarMetadata(String group,String name,String version,String sha256,String confidence){this.group=group;this.name=name;this.version=version;this.sha256=sha256;this.confidence=confidence;}
  static JarMetadata resolve(String location){
    String external=location;
    try {
      // Examples: jar:file:/app.jar!/BOOT-INF/lib/x.jar!/ ; file:/opt/tomcat/webapps/app/WEB-INF/lib/x.jar
      while(external.startsWith("jar:"))external=external.substring(4);
      int sep=external.indexOf("!/");String outer=sep>=0?external.substring(0,sep):external;
      File outerFile=new File(new URI(outer));
      if(!outerFile.isFile())return fallback(location);
      String[] nested=sep>=0?external.substring(sep+2).split("!/"):new String[0];
      byte[] inner=null;
      if(nested.length>0 && !nested[0].isEmpty()){
        String entry=nested[0];
        // Reject encoded traversal or excessive nested entry expansion.
        if(entry.contains("..")||entry.startsWith("/"))return fallback(location);
        try(ZipFile zip=new ZipFile(outerFile)){
          ZipEntry z=zip.getEntry(entry);
          if(z==null || z.isDirectory() || z.getSize()>64L*1024*1024)return fallback(location);
          inner=readCapped(zip.getInputStream(z),64*1024*1024);
        }
      }
      if(inner!=null){return inspectZip(new ByteArrayInputStream(inner),shortName(nested[0]),digest(inner));}
      if(outerFile.getName().toLowerCase(Locale.ROOT).endsWith(".jar")){
        String hash=hashFile(outerFile);
        try(InputStream in=new BufferedInputStream(new FileInputStream(outerFile))){return inspectZip(in,outerFile.getName(),hash);}
      }
      return fallback(location);
    }catch(Throwable ignored){return fallback(location);}
  }
  static JarMetadata fallback(String source){
    String path=source.replace('\\','/');int bang=path.lastIndexOf("!/");if(bang>=0)path=path.substring(bang+2);
    String name=shortName(path);return new JarMetadata(null,name,null,null,"filename-only");
  }
  private static String shortName(String path){if(path==null||path.length()==0)return "unknown";
    int slash=path.lastIndexOf('/');String v=path.substring(slash+1);if(v.isEmpty()){int end=path.lastIndexOf('/',path.length()-2);v=path.substring(end+1).replace("/","");}
    if(v.endsWith(".jar"))v=v.substring(0,v.length()-4);return v.isEmpty()?"unknown":v;
  }
  private static JarMetadata inspectZip(InputStream stream,String fileName,String hash)throws IOException{
    String g=null,a=null,v=null,manifestVersion=null,manifestName=null;
    ZipInputStream zip=new ZipInputStream(stream);try{
      ZipEntry entry;int count=0;
      while((entry=zip.getNextEntry())!=null && count++<30000){
        String n=entry.getName();if(n==null)continue;
        if(n.startsWith("META-INF/maven/")&&n.endsWith("/pom.properties")&&entry.getSize()<65536){
          Properties props=new Properties();props.load(new ByteArrayInputStream(readCapped(zip,65536)));
          String pg=props.getProperty("groupId"),pa=props.getProperty("artifactId"),pv=props.getProperty("version");
          if(pg!=null&&pa!=null&&pv!=null){g=pg;a=pa;v=pv;break;}
        }else if("META-INF/MANIFEST.MF".equalsIgnoreCase(n)){
          Manifest m=new Manifest(new ByteArrayInputStream(readCapped(zip,65536)));
          Attributes attrs=m.getMainAttributes();manifestVersion=trim(attrs.getValue("Implementation-Version"));manifestName=trim(attrs.getValue("Implementation-Title"));
        }
      }
    }finally{zip.close();}
    if(g!=null)return new JarMetadata(g,a,v,hash,"pom.properties");
    return new JarMetadata(null,manifestName!=null?manifestName:shortName(fileName),manifestVersion,hash,manifestVersion!=null?"manifest":"filename-only");
  }
  private static String trim(String v){return v==null||v.trim().isEmpty()?null:v.trim();}
  private static byte[] readCapped(InputStream in,int max)throws IOException {
    ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] b=new byte[8192];int n,total=0;
    while((n=in.read(b))!=-1){total+=n;if(total>max)throw new IOException("uncompressed entry exceeds cap");out.write(b,0,n);}return out.toByteArray();
  }
  private static String digest(byte[] b)throws Exception{return hex(MessageDigest.getInstance("SHA-256").digest(b));}
  private static String hashFile(File f)throws Exception{
    MessageDigest md=MessageDigest.getInstance("SHA-256");try(InputStream in=new BufferedInputStream(new FileInputStream(f))){byte[] buf=new byte[32768];int n;while((n=in.read(buf))!=-1)md.update(buf,0,n);}return hex(md.digest());
  }
  private static String hex(byte[] b){StringBuilder sb=new StringBuilder();for(byte v:b){int x=v&255;if(x<16)sb.append('0');sb.append(Integer.toHexString(x));}return sb.toString();}
}
