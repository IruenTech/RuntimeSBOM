package example;
public class Worker {
  public int compute(int i){try {if(i%2==0)return i+5;return Integer.parseInt(""+i)*3;}catch(NumberFormatException e){return -1;}}
}
