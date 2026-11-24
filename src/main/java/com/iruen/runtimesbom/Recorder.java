package com.iruen.runtimesbom;

/** Method entry hook. Intentionally allocation-light, exception-safe and application-classloader visible. */
public final class Recorder {
  private Recorder(){}
  public static void hit(int eventId){
    try{RuntimeSbomAgent.hit(eventId);}catch(Throwable ignored){}
  }
  public static void hit(String event){
    try{RuntimeSbomAgent.hit(event);}catch(Throwable ignored){}
  }
}
