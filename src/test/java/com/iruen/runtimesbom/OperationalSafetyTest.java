package com.iruen.runtimesbom;
import java.io.File;
import java.nio.file.Files;

/** Exercises recorder sampling, event bound, and local kill-switch without ASM dependency. */
public final class OperationalSafetyTest {
  public static void main(String[] ignored)throws Exception {
    RuntimeSbomAgent.calls.clear();
    RuntimeSbomAgent.sampledOut.set(0);
    RuntimeSbomAgent.sampleEvery=4;
    RuntimeSbomAgent.traceDisabled=false;
    for(int i=0;i<20;i++)Recorder.hit("test|loader=1|Worker#compute(I)I");
    long hits=RuntimeSbomAgent.calls.get("test|loader=1|Worker#compute(I)I").sum();
    if(hits!=5 || RuntimeSbomAgent.sampledOut.get()!=15)
      throw new AssertionError("sampling hits="+hits+" skipped="+RuntimeSbomAgent.sampledOut.get());
    RuntimeSbomAgent.sampleEvery=1;
    File marker=File.createTempFile("runtimesbom-disable-",".flag");
    try {
      RuntimeSbomAgent.killSwitchFile=marker.getAbsolutePath();
      RuntimeSbomAgent.updateKillSwitch();
      if(!RuntimeSbomAgent.traceDisabled)throw new AssertionError("kill switch not active");
      Recorder.hit("test|loader=1|Worker#compute(I)I");
      if(RuntimeSbomAgent.calls.get("test|loader=1|Worker#compute(I)I").sum()!=5)
        throw new AssertionError("disabled recorder accepted an event");
    } finally {Files.deleteIfExists(marker.toPath());}
    RuntimeSbomAgent.updateKillSwitch();
    if(RuntimeSbomAgent.traceDisabled)throw new AssertionError("kill switch not cleared");
    RuntimeSbomAgent.calls.clear();
    RuntimeSbomAgent.maxEvents=100;
    for(int i=0;i<130;i++)Recorder.hit("test|"+i);
    if(RuntimeSbomAgent.calls.size()!=100 || RuntimeSbomAgent.droppedEvents.get()<30)
      throw new AssertionError("event cap not enforced");
    System.out.println("OperationalSafetyTest PASS");
  }
}
