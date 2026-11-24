package com.iruen.runtimesbom;

import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

/** Narrow counter benchmark; excludes bytecode transformation, I/O and full JVM overhead. */
public final class CounterBenchmark {
  static final int THREADS=12, OPERATIONS=150000;
  static final class Result { final long ns; final long count; Result(long n,long c){ns=n;count=c;} }
  interface Counter {void increment();long value();}
  static Result run(final Counter counter)throws Exception {
    ExecutorService exec=Executors.newFixedThreadPool(THREADS);
    final CountDownLatch ready=new CountDownLatch(THREADS);
    final CountDownLatch start=new CountDownLatch(1);
    Future<?>[] workers=new Future<?>[THREADS];
    for(int t=0;t<THREADS;t++)workers[t]=exec.submit(new Runnable(){public void run(){
      ready.countDown();try{start.await();}catch(InterruptedException e){Thread.currentThread().interrupt();return;}
      for(int i=0;i<OPERATIONS;i++)counter.increment();
    }});
    ready.await();long begin=System.nanoTime();start.countDown();
    for(Future<?> f:workers)f.get();long duration=System.nanoTime()-begin;exec.shutdown();
    if(counter.value()!=(long)THREADS*OPERATIONS)throw new AssertionError("incorrect count: "+counter.value());
    return new Result(duration,counter.value());
  }
  public static void main(String[] args)throws Exception {
    for(int trial=0;trial<7;trial++){
      final AtomicLong a=new AtomicLong();
      Result atomic=run(new Counter(){public void increment(){a.incrementAndGet();}public long value(){return a.get();}});
      final LongAdder l=new LongAdder();
      Result adder=run(new Counter(){public void increment(){l.increment();}public long value(){return l.sum();}});
      System.out.println("trial="+trial+" atomic_ns="+atomic.ns+" longadder_ns="+adder.ns+" operations="+atomic.count);
    }
  }
}
