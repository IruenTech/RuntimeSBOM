package example;
public class Demo {
  public static void main(String[] a) throws Exception{
    for(int i=0;i<4;i++)System.out.println("DEMO result="+new Worker().compute(i));
    System.out.println("done");
  }
}
