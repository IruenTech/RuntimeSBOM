package com.iruen.runtimesbom;
public final class MetadataProbe {
  public static void main(String[] args){
    JarMetadata m=JarMetadata.resolve(args[0]);
    System.out.println("group="+m.group+";name="+m.name+";version="+m.version+";confidence="+m.confidence+";sha256="+m.sha256);
  }
}
