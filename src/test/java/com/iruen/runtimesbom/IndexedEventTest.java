package com.iruen.runtimesbom;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
/** Exercises stable integer IDs, bounded registration, and parallel lossless aggregation. */
public final class IndexedEventTest {
  public static void main(String[] args) throws Exception {
    RuntimeSbomAgent.maxEvents=128;
    RuntimeSbomAgent.eventSlots=new AtomicReferenceArray<RuntimeSbomAgent.EventSlot>(129);
    RuntimeSbomAgent.nextEventId.set(0);
    RuntimeSbomAgent.calls.clear();
    RuntimeSbomAgent.traceDisabled=false;
    RuntimeSbomAgent.sampleEvery=1;
    final int id=RuntimeSbomAgent.registerEvent("jar|loader=abc|Worker#run()V");
    if(id!=1)throw new AssertionError("first ID="+id);
    int threads=12, loops=100000;
    ExecutorService pool=Executors.newFixedThreadPool(threads);
    CountDownLatch start=new CountDownLatch(1);
    Future<?>[] future=new Future<?>[threads];
    for(int i=0;i<threads;i++)future[i]=pool.submit(new Runnable(){public void run(){try{start.await();}catch(InterruptedException e){Thread.currentThread().interrupt();return;}for(int j=0;j<100000;j++)Recorder.hit(id);}});
    start.countDown();for(Future<?> f:future)f.get(30,TimeUnit.SECONDS);pool.shutdown();
    long observed=RuntimeSbomAgent.eventSnapshot().get("jar|loader=abc|Worker#run()V");
    if(observed!=1200000L)throw new AssertionError("observed="+observed);
    for(int i=1;i<128;i++)RuntimeSbomAgent.registerEvent("key"+i);
    if(RuntimeSbomAgent.registerEvent("overflow")!=0)throw new AssertionError("registration cap");
    if(RuntimeSbomAgent.nextEventId.get()!=128)throw new AssertionError("event count");
    long before=RuntimeSbomAgent.eventSlots.get(id).counter.sum();
    RuntimeSbomAgent.traceDisabled=true;Recorder.hit(id);
    if(RuntimeSbomAgent.eventSlots.get(id).counter.sum()!=before)throw new AssertionError("kill switch");
    System.out.println("IndexedEventTest PASS 1200000 / 1200000; max=128; kill switch PASS");
  }
}
