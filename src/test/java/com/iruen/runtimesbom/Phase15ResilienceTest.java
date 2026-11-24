package com.iruen.runtimesbom;

import com.sun.net.httpserver.HttpServer;
import java.io.*;
import java.net.*;
import java.nio.file.*;
import java.util.concurrent.atomic.*;

/** Actual loopback HTTP fault injection and loader isolation tests; no external dependencies. */
public final class Phase15ResilienceTest {
  private static void check(boolean ok,String what){if(!ok)throw new AssertionError(what);}
  public static void main(String[] args)throws Exception{
    ClassLoader parent=Phase15ResilienceTest.class.getClassLoader();
    ClassLoader delegated=new ClassLoader(parent){};
    ClassLoader isolated=new ClassLoader(null){};
    check(RuntimeSbomAgent.visibleFrom(delegated),"delegating loader must see identical Recorder");
    check(!RuntimeSbomAgent.visibleFrom(isolated),"isolated loader must be skipped safely");
    File f=File.createTempFile("runtime-sbom-phase15-", ".json");
    Files.write(f.toPath(),"{\"bomFormat\":\"CycloneDX\"}".getBytes("UTF-8"));
    final AtomicInteger requests=new AtomicInteger();
    final AtomicInteger status=new AtomicInteger(503);
    HttpServer server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
    server.createContext("/api/v1/sbom",exchange->{
      try(InputStream in=exchange.getRequestBody()){byte[] buf=new byte[1024];while(in.read(buf)!=-1){}}
      int attempt=requests.incrementAndGet();
      int code=status.get()==503 && attempt>=3?200:status.get();
      exchange.sendResponseHeaders(code,-1);exchange.close();
    });
    server.start();
    String endpoint="http://127.0.0.1:"+server.getAddress().getPort()+"/api/v1/sbom";
    try{
      AtomicLong ok=new AtomicLong(),fail=new AtomicLong();
      CollectorClient.post(f,endpoint,"PHASE15_TEST_TOKEN","was-test",1000,ok,fail);
      check(ok.get()==1&&fail.get()==0&&requests.get()==3,"503 retry then recovery");
      requests.set(0);status.set(401);
      CollectorClient.post(f,endpoint,"PHASE15_TEST_TOKEN","was-test",1000,ok,fail);
      check(ok.get()==1&&fail.get()==1&&requests.get()==1,"401 must never retry");
      requests.set(0);status.set(429);
      CollectorClient.post(f,endpoint,"PHASE15_TEST_TOKEN","was-test",1000,ok,fail);
      check(fail.get()==2&&requests.get()==3,"429 bounded retries");
      System.out.println("PASS loader isolation/delegation; HTTP 503 recovery; 401 no retry; 429 bounded retry");
    }finally{server.stop(0);f.delete();}
  }
}
