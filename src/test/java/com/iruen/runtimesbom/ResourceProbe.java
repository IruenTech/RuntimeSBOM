package com.iruen.runtimesbom;
public final class ResourceProbe {
  private static void check(String resource,String cls,String expected){
    String actual=ResourceResolver.origin(resource,cls);
    if(expected==null?actual!=null:!expected.equals(actual))throw new AssertionError(resource+" => "+actual+" expected "+expected);
  }
  public static void main(String[] args){
    check("jar:file:/apps/boot.jar!/BOOT-INF/lib/demo-1.0.jar!/com/example/Widget.class", "com/example/Widget", "file:/apps/boot.jar!/BOOT-INF/lib/demo-1.0.jar");
    check("jar:nested:/apps/boot.jar/!BOOT-INF/lib/demo-1.0.jar!/com/example/Widget.class", "com.example.Widget", "file:/apps/boot.jar!/BOOT-INF/lib/demo-1.0.jar");
    check("jar:file:/apps/app.war!/WEB-INF/lib/demo.jar!/com/example/Widget.class", "com/example/Widget", "file:/apps/app.war!/WEB-INF/lib/demo.jar");
    check("jar:file:/opt/lib/demo.jar!/com/example/Widget.class", "com/example/Widget", "file:/opt/lib/demo.jar");
    check("file:/opt/app/WEB-INF/classes/com/example/Widget.class", "com/example/Widget", "file:/opt/app/WEB-INF/classes/");
    check("jar:file:/opt/lib/demo.jar!/other/Widget.class", "com/example/Widget", null);
    System.out.println("PASS resource URL attribution parser");
  }
}
