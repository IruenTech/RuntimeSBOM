package com.iruen.runtimesbom;
import java.util.*;

/** Unit test: loader identity and resource relocation may never cross components. */
public final class AttributionIndexTest {
  private static void require(boolean yes,String message){if(!yes)throw new AssertionError(message);}
  public static void main(String[] args){
    Map<String,Long> events=new HashMap<String,Long>();
    events.put("file:/one.jar|loader=aaa|fixture.lib.Helper#compute(I)I",3L);
    events.put("file:/one.jar|loader=bbb|fixture.lib.Helper#compute(I)I",5L);
    events.put("file:/outer.jar|loader=ccc|fixture.lib.Helper#compute(I)I",7L);
    events.put("file:/missing.jar|loader=aaa|fixture.lib.Other#run()V",11L);
    events.put("invalid key without separators",13L);
    Map<String,String> redirects=new HashMap<String,String>();
    redirects.put("file:/outer.jar|loader=ccc|fixture.lib.Helper", "file:/outer.jar!/BOOT-INF/lib/dep.jar");
    Set<String> known=new HashSet<String>(Arrays.asList(
      "file:/one.jar|loader=aaa","file:/one.jar|loader=bbb",
      "file:/outer.jar!/BOOT-INF/lib/dep.jar|loader=ccc"));
    AttributionIndex index=AttributionIndex.build(events,redirects,known);
    require(index.byOrigin.size()==3,"expected three distinct components");
    require(index.byOrigin.get("file:/one.jar|loader=aaa").entries==3,"loader A collapse");
    require(index.byOrigin.get("file:/one.jar|loader=bbb").entries==5,"loader B collapse");
    require(index.byOrigin.get("file:/outer.jar!/BOOT-INF/lib/dep.jar|loader=ccc").entries==7,"nested origin not matched");
    require(index.unattributedEntries==24,"unknown+invalid entries lost");
    require(index.unattributedMethods==2 && index.invalidEvents==1,"invalid evidence tracking");
    System.out.println("AttributionIndexTest PASS: exact loader, nested origin, unbound diagnostics");
  }
}
