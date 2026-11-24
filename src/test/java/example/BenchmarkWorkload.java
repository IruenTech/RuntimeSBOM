package example;
import java.lang.management.*;
/** Deterministic synthetic CPU workload; records CPU, heap and GC deltas per isolated JVM. */
public final class BenchmarkWorkload {
  public static void main(String[] args) {
    int n = Integer.parseInt(args.length == 0 ? "200000" : args[0]);
    Worker w = new Worker();
    ThreadMXBean thread=ManagementFactory.getThreadMXBean();
    boolean cpu=thread.isCurrentThreadCpuTimeSupported();
    if(cpu && !thread.isThreadCpuTimeEnabled())try{thread.setThreadCpuTimeEnabled(true);}catch(SecurityException ignored){cpu=false;}
    long beforeCpu=cpu?thread.getCurrentThreadCpuTime():-1;
    long beforeHeap=ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    long beforeGcCount=0,beforeGcMs=0;
    for(GarbageCollectorMXBean gc:ManagementFactory.getGarbageCollectorMXBeans()){
      beforeGcCount+=Math.max(0,gc.getCollectionCount());beforeGcMs+=Math.max(0,gc.getCollectionTime());
    }
    long sum=0,begin=System.nanoTime();
    for(int i=0;i<n;i++)sum+=w.compute(i%1000);
    long elapsed=System.nanoTime()-begin;
    long afterCpu=cpu?thread.getCurrentThreadCpuTime():-1;
    long afterHeap=ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    long afterGcCount=0,afterGcMs=0;
    for(GarbageCollectorMXBean gc:ManagementFactory.getGarbageCollectorMXBeans()){
      afterGcCount+=Math.max(0,gc.getCollectionCount());afterGcMs+=Math.max(0,gc.getCollectionTime());
    }
    System.out.println("BENCHMARK iterations="+n+" checksum="+sum+" elapsedNs="+elapsed);
    System.out.println("BENCHMETRICS cpuNs="+(cpu?afterCpu-beforeCpu:-1)+" heapDeltaBytes="+(afterHeap-beforeHeap)+" gcCount="+(afterGcCount-beforeGcCount)+" gcMs="+(afterGcMs-beforeGcMs));
  }
}
