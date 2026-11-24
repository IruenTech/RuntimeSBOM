package com.iruen.runtimesbom;

import java.io.*;
import java.lang.instrument.*;
import java.net.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.jar.*;
import java.util.zip.*;

/** Java 8-compatible, fail-open runtime provenance + opt-in method entry agent. */
public final class RuntimeSbomAgent {
  static final ConcurrentMap<String,Origin> origins=new ConcurrentHashMap<String,Origin>();
  static final ConcurrentMap<String,LongAdder> calls=new ConcurrentHashMap<String,LongAdder>();
  static final Object eventInsertionLock=new Object();
  // Bounded integer dispatch: event signatures are allocated at transform time, never on entry.
  // 0 is reserved for a dropped event; each EventSlot is safely published through AtomicReferenceArray.
  static final AtomicInteger nextEventId=new AtomicInteger();
  static volatile AtomicReferenceArray<EventSlot> eventSlots=new AtomicReferenceArray<EventSlot>(50001);
  static final AtomicLong registrationDrops=new AtomicLong();
  static final class EventSlot {
    final String signature; final LongAdder counter=new LongAdder();
    EventSlot(String signature){this.signature=signature;}
  }
  static int registerEvent(String signature){
    synchronized(eventInsertionLock){
      int next=nextEventId.get()+1;
      if(next>=eventSlots.length() || calls.size()+next>maxEvents){registrationDrops.incrementAndGet();return 0;}
      eventSlots.set(next,new EventSlot(signature));
      nextEventId.set(next);
      return next;
    }
  }
  static void hit(int eventId){
    if(eventId<=0 || traceDisabled)return;
    if(sampleEvery>1){
      int[] counter=sampleIndex.get();counter[0]++;
      if(counter[0]<sampleEvery){sampledOut.incrementAndGet();return;}
      counter[0]=0;
    }
    AtomicReferenceArray<EventSlot> slots=eventSlots;
    if(eventId>=slots.length())return;
    EventSlot event=slots.get(eventId);
    if(event!=null)event.counter.increment();
  }
  static Map<String,Long> eventSnapshot(){
    Map<String,Long> snapshot=new LinkedHashMap<String,Long>();
    for(Map.Entry<String,LongAdder> e:calls.entrySet())snapshot.put(e.getKey(),e.getValue().sum());
    AtomicReferenceArray<EventSlot> slots=eventSlots;
    for(int i=1;i<=nextEventId.get() && i<slots.length();i++){
      EventSlot e=slots.get(i);
      if(e!=null && e.counter.sum()>0){Long prev=snapshot.get(e.signature);snapshot.put(e.signature,(prev==null?0L:prev)+e.counter.sum());}
    }
    return snapshot;
  }

  static final AtomicLong skippedTransforms=new AtomicLong(), successfulTransforms=new AtomicLong(), observedClasses=new AtomicLong();
  static volatile String output="runtime-sbom.json";
  static volatile String[] tracedPackages=new String[0];
  static volatile int interval=30;
  static volatile int maxEvents=50000;
  // Safe defaults: profiling is opt-in and constrained to a bounded surface.
  static volatile int sampleEvery=1, maxTransformedClasses=10000, maxTransformErrors=100;
  static volatile String killSwitchFile="";
  static volatile boolean traceDisabled=false;
  static final AtomicLong sampledOut=new AtomicLong(), droppedEvents=new AtomicLong();
  static final AtomicLong transformFailures=new AtomicLong(), transformerDisabled=new AtomicLong();
  static final AtomicLong classLoaderVisible=new AtomicLong(), classLoaderIsolated=new AtomicLong();
  static final ThreadLocal<int[]> sampleIndex=new ThreadLocal<int[]>() {
    @Override protected int[] initialValue(){return new int[]{0};}
  };
  static volatile String agentLocation="";
  static volatile boolean trackMethods=false;
  static volatile boolean resourceProbe=true;
  static volatile String engine="asm";
  static volatile String collectorUrl="";
  static volatile String collectorTokenEnv="RUNTIMESBOM_TOKEN";
  static volatile String assetId="default";
  static volatile int httpTimeoutMs=3000;
  static volatile String queueDir="";
  static volatile int maxQueueFiles=512, queueDrainBatch=8, queueDrainInterval=15;
  static volatile long maxQueueBytes=64L*1024*1024;
  static volatile DurableDeliveryQueue deliveryQueue;
  static final AtomicLong uploadSuccess=new AtomicLong(),uploadFailures=new AtomicLong();
  static final ConcurrentLinkedQueue<Probe> probes=new ConcurrentLinkedQueue<Probe>();
  static final AtomicLong probed=new AtomicLong(), resolved=new AtomicLong(), failedProbe=new AtomicLong();
  static final int MAX_PENDING=10000;
  static final ConcurrentMap<String,String> classOriginOverride=new ConcurrentHashMap<String,String>();
  static final AtomicBoolean started=new AtomicBoolean(),writing=new AtomicBoolean();
  private RuntimeSbomAgent(){}
  public static void premain(String args,Instrumentation inst){start(args,inst);}
  public static void agentmain(String args,Instrumentation inst){start(args,inst);}

  private static void start(String args,Instrumentation inst){
    if(!started.compareAndSet(false,true))return;
    if(args!=null)for(String s:args.split(",")){
      int eq=s.indexOf('=');if(eq<1)continue;String key=s.substring(0,eq).trim(),value=s.substring(eq+1).trim();
      if("output".equals(key)&&!value.isEmpty())output=value;
      if("interval".equals(key))try{interval=Math.max(0,Integer.parseInt(value));}catch(NumberFormatException ignored){}
      if("resourceProbe".equals(key))resourceProbe=Boolean.parseBoolean(value);
      if("engine".equals(key))engine=value;
      if("collectorUrl".equals(key))collectorUrl=value;
      if("collectorTokenEnv".equals(key))collectorTokenEnv=value;
      if("assetId".equals(key) && value.matches("[a-zA-Z0-9._:-]{1,128}"))assetId=value;
      if("queueDir".equals(key))queueDir=value;
      if("maxQueueFiles".equals(key))try{maxQueueFiles=Math.max(1,Math.min(10000,Integer.parseInt(value)));}catch(NumberFormatException ignored){}
      if("maxQueueBytes".equals(key))try{maxQueueBytes=Long.parseLong(value);}catch(NumberFormatException ignored){}
      if("queueDrainBatch".equals(key))try{queueDrainBatch=Math.max(1,Math.min(100,Integer.parseInt(value)));}catch(NumberFormatException ignored){}
      if("queueDrainInterval".equals(key))try{queueDrainInterval=Math.max(5,Math.min(3600,Integer.parseInt(value)));}catch(NumberFormatException ignored){}
      if("httpTimeoutMs".equals(key))try{httpTimeoutMs=Math.max(500,Math.min(30000,Integer.parseInt(value)));}catch(NumberFormatException ignored){}
      if("maxEvents".equals(key))try{maxEvents=Math.max(100,Math.min(100000,Integer.parseInt(value)));}catch(NumberFormatException ignored){}
      if("sampleEvery".equals(key))try{sampleEvery=Math.max(1,Math.min(100000,Integer.parseInt(value)));}catch(NumberFormatException ignored){}
      if("maxTransformedClasses".equals(key))try{maxTransformedClasses=Math.max(1,Math.min(1000000,Integer.parseInt(value)));}catch(NumberFormatException ignored){}
      if("maxTransformErrors".equals(key))try{maxTransformErrors=Math.max(1,Math.min(1000000,Integer.parseInt(value)));}catch(NumberFormatException ignored){}
      if("killSwitchFile".equals(key))killSwitchFile=value;
      if("tracePackages".equals(key)){
        if(!value.isEmpty())tracedPackages=value.replace('.','/').split(";");
      }
    }
    if(!collectorUrl.isEmpty()){
      try{deliveryQueue=new DurableDeliveryQueue(new File(queueDir.isEmpty()?output+".spool":queueDir),maxQueueFiles,maxQueueBytes);}
      catch(IOException ex){System.err.println("[RuntimeSBOM] durable queue disabled: "+ex.getMessage());}
    }
    // Create a strictly bounded slot table once, before any transformer can register events.
    eventSlots=new AtomicReferenceArray<EventSlot>(maxEvents+1);
    trackMethods=tracedPackages.length>0;
    updateKillSwitch();
    try{agentLocation=RuntimeSbomAgent.class.getProtectionDomain().getCodeSource().getLocation().toExternalForm();}catch(Throwable ignored){}
    inst.addTransformer(new ClassFileTransformer(){
      @Override public byte[] transform(ClassLoader loader,String className,Class<?> redef,ProtectionDomain domain,byte[] bytecode){
        try {
          if(className==null||className.startsWith("com/iruen/runtimesbom/")||className.startsWith("java/")
             ||className.startsWith("javax/")||className.startsWith("jdk/")||className.startsWith("sun/"))return null;
          String source=source(domain);
          if(source.length()==0 && resourceProbe && loader!=null && probes.size()<MAX_PENDING) {
            probes.offer(new Probe(loader,className,""));
          }
          if(source.length()>0&&!source.equals(agentLocation)){
            String key=key(source,loader);
            Origin orig=origins.get(key);
            if(orig==null){Origin proposed=new Origin(source,loader);Origin existing=origins.putIfAbsent(key,proposed);orig=existing==null?proposed:existing;}
            orig.loaded.incrementAndGet(); observedClasses.incrementAndGet();
            if(resourceProbe&&loader!=null&&probes.size()<MAX_PENDING)probes.offer(new Probe(loader,className,source));
          }
          // The ASM transformer is registered separately and handles method-entry probes.
          // This transformer only observes provenance, never edits bytecode.
        }catch(Throwable ignored){skippedTransforms.incrementAndGet();}
        return null;
      }
    },false);
    if(trackMethods){
      if(!"asm".equals(engine))System.err.println("[RuntimeSBOM] unsupported engine="+engine+"; method instrumentation disabled");
      else try {
        inst.addTransformer(new AsmTransformer(),false);
      }catch(Throwable t){System.err.println("[RuntimeSBOM] ASM unavailable; method instrumentation disabled: "+t);}
    }
    // Attach mode and preload evidence: loaded classes may be known, but entry instrumentation is NOT retroactive.
    try{for(Class<?> c:inst.getAllLoadedClasses()){
      try{if(c==null||c.isArray()||c.isPrimitive()||c.getName().startsWith("com.iruen.runtimesbom."))continue;
        String s=source(c.getProtectionDomain());if(!s.isEmpty()&&s.equals(agentLocation))continue;
        if(resourceProbe && s.length()==0){try{URL url=c.getResource("/"+c.getName().replace('.','/')+".class");String r=ResourceResolver.origin(url==null?null:url.toExternalForm(),c.getName());if(r!=null&&!r.isEmpty())s=r;}catch(Throwable ignored){}}
        if(s.length()==0)continue;
        String k=key(s,c.getClassLoader());Origin o=origins.get(k);
        if(o==null){Origin newO=new Origin(s,c.getClassLoader());Origin prior=origins.putIfAbsent(k,newO);o=prior==null?newO:prior;}
        o.preloaded.incrementAndGet();
      }catch(Throwable ignored){}
    }}catch(Throwable ignored){}
    Runtime.getRuntime().addShutdownHook(new Thread(new Runnable(){public void run(){write();drainDeliveryQueue(true);}},"runtime-sbom-shutdown"));
    if(deliveryQueue!=null){
      ScheduledExecutorService sender=Executors.newSingleThreadScheduledExecutor(new ThreadFactory(){
        public Thread newThread(Runnable r){Thread t=new Thread(r,"runtime-sbom-delivery");t.setDaemon(true);return t;}
      });
      sender.scheduleWithFixedDelay(new Runnable(){public void run(){drainDeliveryQueue();}},0,queueDrainInterval,TimeUnit.SECONDS);
    }
    if(interval>0){ScheduledExecutorService ex=Executors.newSingleThreadScheduledExecutor(new ThreadFactory(){public Thread newThread(Runnable r){Thread t=new Thread(r,"runtime-sbom-snapshot");t.setDaemon(true);return t;}});
      ex.scheduleAtFixedRate(new Runnable(){public void run(){write();}},interval,interval,TimeUnit.SECONDS);
    }
    System.err.println("[RuntimeSBOM] Phase23 ASM configured, methodTrace="+trackMethods+", output="+output);
  }
  static void drainDeliveryQueue(){drainDeliveryQueue(false);}
  static void drainDeliveryQueue(boolean shutdown){
    DurableDeliveryQueue q=deliveryQueue;
    if(q==null)return;
    if(shutdown)q.drainForShutdown(collectorUrl,collectorTokenEnv,httpTimeoutMs,queueDrainBatch);
    else q.drain(collectorUrl,collectorTokenEnv,httpTimeoutMs,queueDrainBatch);
    uploadSuccess.set(q.delivered.get());
    uploadFailures.set(q.deliveryFailures.get());
  }
  static String safeProperty(String name){
    try { String value=System.getProperty(name);return value==null?"unknown":value; }
    catch(SecurityException ignored) { return "restricted"; }
  }
  static String source(ProtectionDomain pd){try{if(pd==null||pd.getCodeSource()==null||pd.getCodeSource().getLocation()==null)return "";
    return pd.getCodeSource().getLocation().toExternalForm();}catch(Throwable t){return "";}}
  static boolean visibleFrom(ClassLoader loader){
    try{return Class.forName("com.iruen.runtimesbom.Recorder",false,loader)==Recorder.class;}catch(Throwable t){return false;}
  }
  static String key(String source,ClassLoader loader){return source+"|loader="+(loader==null?"bootstrap":Integer.toHexString(System.identityHashCode(loader)));}
  static void hit(String event){
    if(event==null || traceDisabled)return;
    if(sampleEvery>1){
      int[] counter=sampleIndex.get();counter[0]++;
      if(counter[0]<sampleEvery){sampledOut.incrementAndGet();return;}
      counter[0]=0;
    }
    LongAdder n=calls.get(event);
    if(n==null){
      // Serialize only first sightings. This guarantees the cardinality ceiling
      // even when many threads encounter new method signatures simultaneously.
      synchronized(eventInsertionLock){
        n=calls.get(event);
        if(n==null){
          if(calls.size()+nextEventId.get()>=maxEvents){droppedEvents.incrementAndGet();return;}
          n=new LongAdder();
          calls.put(event,n);
        }
      }
    }
    n.increment();
  }
  static void updateKillSwitch(){
    if(killSwitchFile.length()==0)return;
    try {traceDisabled=Files.isRegularFile(Paths.get(killSwitchFile));}
    catch(Throwable t){traceDisabled=true;}
  }
  static final class Origin {
    final String source,loader,loaderChain,loaderKey; final AtomicLong loaded=new AtomicLong(),preloaded=new AtomicLong();
    Origin(String s,ClassLoader l){source=s;loaderKey=key(s,l);loader=l==null?"bootstrap":l.getClass().getName()+"@"+Integer.toHexString(System.identityHashCode(l));loaderChain=loaderChain(l);}
    private static String loaderChain(ClassLoader l){StringBuilder b=new StringBuilder();int depth=0;
      try{while(l!=null&&depth++<16){if(b.length()>0)b.append(" <- ");b.append(l.getClass().getName()).append('@').append(Integer.toHexString(System.identityHashCode(l)));l=l.getParent();}if(l!=null)b.append(" <- ...");}
      catch(Throwable ignored){b.append(" [parent inaccessible]");}return b.toString();}
  }
  static final class Probe {
    final java.lang.ref.WeakReference<ClassLoader> loader;
    final String className, source;
    Probe(ClassLoader l,String c,String s){loader=new java.lang.ref.WeakReference<ClassLoader>(l);className=c;source=s;}
  }
  static void resolveProbes(){
    Probe p;int scanned=0;
    while((p=probes.poll())!=null && scanned++<MAX_PENDING){
      probed.incrementAndGet();
      try{
        ClassLoader l=p.loader.get();if(l==null)continue;
        URL url=l.getResource(p.className+".class");
        String origin=ResourceResolver.origin(url==null?null:url.toExternalForm(),p.className);
        if(origin==null || origin.equals(p.source))continue;
        // Only trust class-resource relocation within the SAME outer archive. Avoid
        // false matches when parent-first loader.getResource returns another JAR.
        String sourceBase=ResourceResolver.canonical(p.source);
        String candidate=ResourceResolver.canonical(origin);
        if(!sourceBase.isEmpty() && !candidate.startsWith(sourceBase+"!/"))continue;
        if(!candidate.startsWith("file:"))continue;
        Origin old=origins.get(key(p.source,l));
        // Add corrected provenance without double counting the same class-load observation.
        Origin current=origins.get(key(origin,l));
        if(current==null){Origin fresh=new Origin(origin,l);Origin prior=origins.putIfAbsent(key(origin,l),fresh);current=prior==null?fresh:prior;}
        current.loaded.incrementAndGet();
        if(!p.source.isEmpty())classOriginOverride.put(key(p.source,l)+"|"+p.className.replace('/','.'),origin);
        if(old!=null)old.loaded.updateAndGet(v->v>0?v-1:0);
        resolved.incrementAndGet();
      }catch(Throwable ignored){failedProbe.incrementAndGet();}
    }
  }
  static void write(){if(!writing.compareAndSet(false,true))return;try{
    updateKillSwitch();
    if(resourceProbe)resolveProbes();
    Map<String,Long> eventCounts=eventSnapshot();
    List<Origin> records=new ArrayList<Origin>();for(Origin o:origins.values())if(o.loaded.get()>0||o.preloaded.get()>0)records.add(o);Collections.sort(records,new Comparator<Origin>(){public int compare(Origin a,Origin b){int c=a.source.compareTo(b.source);return c!=0?c:a.loader.compareTo(b.loader);}});
    File dest=new File(output).getAbsoluteFile();File dir=dest.getParentFile();if(dir!=null)dir.mkdirs();
    File temp=new File(dir,dest.getName()+".tmp");
    // Assemble exact source+loader attribution once, not once for each component.
    Set<String> originKeys=new HashSet<String>();
    Map<String,JarMetadata> metadataCache=new HashMap<String,JarMetadata>();
    Map<String,String> purlFirstHash=new HashMap<String,String>();
    Set<String> conflictingPurls=new HashSet<String>();
    for(Origin origin:records){
      originKeys.add(origin.loaderKey);
      if(!metadataCache.containsKey(origin.source))
        metadataCache.put(origin.source,JarMetadata.resolve(origin.source));
      JarMetadata meta=metadataCache.get(origin.source);
      if(meta.group!=null && meta.version!=null && meta.sha256!=null){
        String purl="pkg:maven/"+meta.group+"/"+meta.name+"@"+meta.version;
        String first=purlFirstHash.putIfAbsent(purl,meta.sha256);
        if(first!=null && !first.equals(meta.sha256))conflictingPurls.add(purl);
      }
    }
    AttributionIndex attributed=AttributionIndex.build(eventCounts,classOriginOverride,originKeys);
    long attributableEntries=0L;
    for (AttributionIndex.Summary summary : attributed.byOrigin.values()) attributableEntries += summary.entries;
    ObservationQuality.Result observationQuality=ObservationQuality.assess(
        trackMethods, traceDisabled, attributableEntries, sampleEvery,
        transformFailures.get(), classLoaderIsolated.get(), registrationDrops.get(),
        droppedEvents.get(), attributed.unattributedEntries, attributed.invalidEvents);
    Writer w=new BufferedWriter(new OutputStreamWriter(new FileOutputStream(temp),"UTF-8"));
    try{
      w.write("{\"bomFormat\":\"CycloneDX\",\"specVersion\":\"1.6\",\"version\":1,\"metadata\":{\"tools\":{\"components\":[{\"type\":\"application\",\"name\":\"RuntimeSBOM-Agent\",\"version\":\"1.0.0-rc16\"}]},\"properties\":[");
      prop(w,"runtimeSbom:transformedClasses",Long.toString(successfulTransforms.get()),true);
      prop(w,"runtimeSbom:observedClasses",Long.toString(observedClasses.get()),false);
      prop(w,"runtimeSbom:skippedTransforms",Long.toString(skippedTransforms.get()),false);
      prop(w,"runtimeSbom:methodEvents",Integer.toString(eventCounts.size()),false);
      prop(w,"runtimeSbom:observationQuality",observationQuality.level,false);
      prop(w,"runtimeSbom:observationLimitations",observationQuality.reasonCodes(),false);
      prop(w,"runtimeSbom:attributedMethodEntries",Long.toString(attributableEntries),false);
      prop(w,"runtimeSbom:traceMode",trackMethods?"METHOD_ENTRY_REQUESTED":"LOADING_ONLY",false);
      prop(w,"runtimeSbom:unattributedMethodEntries",Long.toString(attributed.unattributedEntries),false);
      prop(w,"runtimeSbom:unattributedDistinctMethods",Integer.toString(attributed.unattributedMethods),false);
      prop(w,"runtimeSbom:invalidMethodEventKeys",Integer.toString(attributed.invalidEvents),false);
      prop(w,"runtimeSbom:conflictingMavenPurls",Integer.toString(conflictingPurls.size()),false);
      prop(w,"runtimeSbom:attributionAlgorithm","source+loader+method",false);
      prop(w,"runtimeSbom:counterImplementation","LongAdder+integerEventId",false);
      prop(w,"runtimeSbom:registeredMethodIds",Integer.toString(nextEventId.get()),false);
      prop(w,"runtimeSbom:registrationDrops",Long.toString(registrationDrops.get()),false);
      prop(w,"runtimeSbom:maxEvents",Integer.toString(maxEvents),false);
      prop(w,"runtimeSbom:sampleEvery",Integer.toString(sampleEvery),false);
      prop(w,"runtimeSbom:observedHitsAreSampled",Boolean.toString(sampleEvery>1),false);
      prop(w,"runtimeSbom:sampledOut",Long.toString(sampledOut.get()),false);
      prop(w,"runtimeSbom:droppedEvents",Long.toString(droppedEvents.get()),false);
      prop(w,"runtimeSbom:transformFailures",Long.toString(transformFailures.get()),false);
      prop(w,"runtimeSbom:transformerDisabled",Long.toString(transformerDisabled.get()),false);
      prop(w,"runtimeSbom:classLoaderVisible",Long.toString(classLoaderVisible.get()),false);
      prop(w,"runtimeSbom:classLoaderIsolated",Long.toString(classLoaderIsolated.get()),false);
      prop(w,"runtimeSbom:agentVersion","1.0.0-rc16",false);
      prop(w,"runtimeSbom:jvmVersion",safeProperty("java.version"),false);
      prop(w,"runtimeSbom:jvmVendor",safeProperty("java.vendor"),false);
      prop(w,"runtimeSbom:osName",safeProperty("os.name"),false);
      prop(w,"runtimeSbom:osArch",safeProperty("os.arch"),false);
      prop(w,"runtimeSbom:traceDisabled",Boolean.toString(traceDisabled),false);
      prop(w,"runtimeSbom:uploadSuccess",Long.toString(uploadSuccess.get()),false);
      prop(w,"runtimeSbom:uploadFailures",Long.toString(uploadFailures.get()),false);
      DurableDeliveryQueue q=deliveryQueue;
      if(q!=null){
        prop(w,"runtimeSbom:queuePendingFiles",Integer.toString(q.pendingFiles()),false);
        prop(w,"runtimeSbom:queuePendingBytes",Long.toString(q.pendingBytes()),false);
        prop(w,"runtimeSbom:queueEnqueued",Long.toString(q.enqueued.get()),false);
        prop(w,"runtimeSbom:queueDelivered",Long.toString(q.delivered.get()),false);
        prop(w,"runtimeSbom:queueRejected",Long.toString(q.enqueueRejected.get()),false);
        prop(w,"runtimeSbom:queueDeliveryFailures",Long.toString(q.deliveryFailures.get()),false);
      }
      prop(w,"runtimeSbom:resourceProbes",Long.toString(probed.get()),false);
      prop(w,"runtimeSbom:resourceResolved",Long.toString(resolved.get()),false);
      prop(w,"runtimeSbom:resourceProbeFailures",Long.toString(failedProbe.get()),false);
      for(Map.Entry<String,Long> e:eventCounts.entrySet())prop(w,"runtimeSbom:methodEntry:"+e.getKey(),Long.toString(e.getValue()),false);
      w.write("]},\"components\":[");
      int idx=0;for(Origin origin:records){
        JarMetadata meta=metadataCache.get(origin.source);
        if(idx++>0)w.write(',');w.write("{\"type\":\"");w.write(origin.source.contains(".jar")||origin.source.contains(".war")||origin.source.contains(".ear")?"library":"application");w.write("\",\"bom-ref\":");q(w,"runtime:"+origin.source+"@"+origin.loader);
        w.write(",\"name\":");q(w,meta.name);if(meta.version!=null){w.write(",\"version\":");q(w,meta.version);}
        if(meta.group!=null && meta.version!=null){w.write(",\"purl\":");q(w,"pkg:maven/"+meta.group+"/"+meta.name+"@"+meta.version);}
        if(meta.sha256!=null){w.write(",\"hashes\":[{\"alg\":\"SHA-256\",\"content\":");q(w,meta.sha256);w.write("}]");}
        w.write(",\"properties\":[");
        prop(w,"runtimeSbom:source",origin.source,true);prop(w,"runtimeSbom:classLoader",origin.loader,false);
        prop(w,"runtimeSbom:classLoaderChain",origin.loaderChain,false);
        prop(w,"runtimeSbom:loadedClassEvents",Long.toString(origin.loaded.get()),false);
        prop(w,"runtimeSbom:preloadedClassCount",Long.toString(origin.preloaded.get()),false);
        prop(w,"runtimeSbom:metadataConfidence",meta.confidence,false);
        if(meta.group!=null && meta.version!=null)
          prop(w,"runtimeSbom:purlHasDifferentHashes",Boolean.toString(conflictingPurls.contains("pkg:maven/"+meta.group+"/"+meta.name+"@"+meta.version)),false);
        AttributionIndex.Summary summary=attributed.byOrigin.get(origin.loaderKey);
        long total=summary==null?0L:summary.entries;
        int methods=summary==null?0:summary.distinctMethods;
        prop(w,"runtimeSbom:observedMethodEntryCount",Long.toString(total),false);
        prop(w,"runtimeSbom:observedDistinctMethods",Integer.toString(methods),false);
        prop(w,"runtimeSbom:runtimeEvidenceState",total>0?"METHOD_EXECUTED":(origin.loaded.get()>0?"CLASS_LOADED":"PRELOADED"),false);
        w.write("]}");
      }
      w.write("],\"compositions\":[{\"aggregate\":\"incomplete\",\"assemblies\":[");
      for(int i=0;i<records.size();i++){if(i>0)w.write(',');q(w,"runtime:"+records.get(i).source+"@"+records.get(i).loader);}w.write("]}],\"properties\":[");
      int n=0;for(Map.Entry<String,Long> e:eventCounts.entrySet()){
        if(n++>0)w.write(',');prop(w,"runtimeSbom:methodEntry:"+e.getKey(),Long.toString(e.getValue()),true);
      }
      w.write("]}");
    }finally{w.close();}
    try{Files.move(temp.toPath(),dest.toPath(),StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);}
    catch(AtomicMoveNotSupportedException ex){Files.move(temp.toPath(),dest.toPath(),StandardCopyOption.REPLACE_EXISTING);}
    System.err.println("[RuntimeSBOM] wrote "+records.size()+" provenance sources to "+dest);
    if(collectorUrl.length()>0){
      DurableDeliveryQueue q=deliveryQueue;
      if(q!=null)q.enqueue(dest,assetId);
      else System.err.println("[RuntimeSBOM] collector configured, but spool unavailable; SBOM remains at "+dest);
    }
  }catch(Throwable t){System.err.println("[RuntimeSBOM] write failed: "+t);}finally{writing.set(false);}}
  private static void prop(Writer w,String name,String val,boolean first)throws IOException {if(!first)w.write(',');w.write("{\"name\":");q(w,name);w.write(",\"value\":");q(w,val);w.write('}');}
  private static void q(Writer w,String s)throws IOException {w.write('"');if(s!=null)for(int i=0;i<s.length();i++){
    char c=s.charAt(i);if(c=='"'||c=='\\'){w.write('\\');w.write(c);}else if(c=='\n')w.write("\\n");else if(c=='\r')w.write("\\r");else if(c=='\t')w.write("\\t");else if(c<32){String h=Integer.toHexString(c);w.write("\\u");for(int z=h.length();z<4;z++)w.write('0');w.write(h);}else w.write(c);
  }w.write('"');}
}
