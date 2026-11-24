package com.iruen.runtimesbom;
/** Diagnostic microbenchmark; not a statistically sound production overhead measurement. */
public final class RecorderBench {
  static volatile long sink;
  public static void main(String[] args){
    int n=args.length==0?1000000:Integer.parseInt(args[0]);
    for(int k=0;k<3;k++){long t=System.nanoTime(); for(int i=0;i<n;i++)sink+=i; if(k==2)System.out.println("baseline_ns_per_call="+((System.nanoTime()-t)/(double)n));}
    RuntimeSbomAgent.sampleEvery=1;
    for(int k=0;k<3;k++){long t=System.nanoTime();for(int i=0;i<n;i++)Recorder.hit("bench|method");if(k==2)System.out.println("recorder_ns_per_call="+((System.nanoTime()-t)/(double)n));}
    RuntimeSbomAgent.sampleEvery=100;
    for(int k=0;k<3;k++){long t=System.nanoTime();for(int i=0;i<n;i++)Recorder.hit("bench|method");if(k==2)System.out.println("recorder_sample100_ns_per_call="+((System.nanoTime()-t)/(double)n));}
    System.out.println("Note: this only measures Recorder.hit; it does not measure class transformation or WAS throughput.");
  }
}
