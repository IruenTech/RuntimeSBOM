package com.iruen.runtimesbom;

import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;

/** Concurrent counter, bounded cardinality and disabled tracing regression checks. */
public final class ConcurrencyStressTest {
  public static void main(String[] args) throws Exception {
    final int threads=12, iterations=100000;
    RuntimeSbomAgent.calls.clear();
    RuntimeSbomAgent.sampleEvery=1;
    RuntimeSbomAgent.maxEvents=256;
    RuntimeSbomAgent.traceDisabled=false;
    runParallel(threads, new Job(){public void run(int t){
      for(int i=0;i<iterations;i++)Recorder.hit("fixture|loader=one|Worker#compute(I)I");
    }});
    long actual=RuntimeSbomAgent.calls.get("fixture|loader=one|Worker#compute(I)I").sum();
    if(actual!=(long)threads*iterations)throw new AssertionError("concurrent count "+actual);
    RuntimeSbomAgent.calls.clear();
    RuntimeSbomAgent.maxEvents=64;
    runParallel(threads,new Job(){public void run(int t){
      for(int i=0;i<3000;i++)Recorder.hit("distinct#"+t+"#"+i);
    }});
    if(RuntimeSbomAgent.calls.size()!=64)throw new AssertionError("cardinality " + RuntimeSbomAgent.calls.size());
    RuntimeSbomAgent.traceDisabled=true;
    int before=RuntimeSbomAgent.calls.size();
    Recorder.hit("disabled#should-not-appear");
    if(RuntimeSbomAgent.calls.size()!=before)throw new AssertionError("kill switch failed");
    RuntimeSbomAgent.traceDisabled=false;
    System.out.println("ConcurrencyStressTest PASS 12 threads x 100000=1200000 events; cap=64");
  }
  interface Job {void run(int index);}
  static void runParallel(int threadCount, final Job job)throws Exception{
    ExecutorService pool=Executors.newFixedThreadPool(threadCount);
    CountDownLatch gate=new CountDownLatch(1);
    AtomicReference<Throwable> problem=new AtomicReference<Throwable>();
    Future<?>[] tasks=new Future<?>[threadCount];
    for(int i=0;i<threadCount;i++){
      final int index=i;
      tasks[i]=pool.submit(new Runnable(){public void run(){try{gate.await();job.run(index);}catch(Throwable e){problem.compareAndSet(null,e);}}});
    }
    gate.countDown();
    for(Future<?> task:tasks)task.get(30,TimeUnit.SECONDS);
    pool.shutdown();
    if(problem.get()!=null)throw new AssertionError(problem.get());
  }
}
