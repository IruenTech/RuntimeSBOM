package com.iruen.runtimesbom;

import java.net.URL;
import java.util.Locale;

/** Converts a class resource URL to its containing archive URL without reading class data. */
final class ResourceResolver {
  private ResourceResolver() {}
  static String origin(String resourceUrl, String binaryName) {
    if (resourceUrl == null || binaryName == null) return null;
    String path = binaryName.replace('.', '/') + ".class";
    String u = resourceUrl.replace("\\", "/");
    if (!u.endsWith(path)) return null;
    String prefix = u.substring(0, u.length() - path.length());
    // Boot 2: jar:file:/app.jar!/BOOT-INF/lib/a.jar!/org/.../Type.class
    // Boot 3: jar:nested:/app.jar/!BOOT-INF/lib/a.jar!/org/.../Type.class
    int nested = prefix.lastIndexOf(".jar!/");
    if (nested >= 0) return canonical(prefix.substring(0, nested + 6));
    int war = prefix.lastIndexOf(".war!/");
    if (war >= 0) return canonical(prefix.substring(0, war + 6));
    int ear = prefix.lastIndexOf(".ear!/");
    if (ear >= 0) return canonical(prefix.substring(0, ear + 6));
    // Expanded WAR, directory classes, or normal file:/lib/foo.jar!/Type.class
    if (prefix.endsWith("!/")) return canonical(prefix);
    if (prefix.startsWith("file:")) return prefix;
    return null;
  }
  static String canonical(String value) {
    String v=value;
    while(v.startsWith("jar:"))v=v.substring(4);
    // Spring Boot 3 nested: nested:/app.jar/!BOOT-INF/lib/foo.jar!/  -> file:/app.jar!/BOOT-INF/lib/foo.jar!/
    if(v.startsWith("nested:")) {
      v=v.substring(7);
      if(v.startsWith("//"))v=v.substring(1);
      if(v.startsWith("/"))v="file:"+v;
      v=v.replace("/!BOOT-INF/", "!/BOOT-INF/").replace("/!WEB-INF/", "!/WEB-INF/");
    }
    if(v.endsWith("!/"))v=v.substring(0,v.length()-2);
    if(v.endsWith("!"))v=v.substring(0,v.length()-1);
    return v;
  }
}
