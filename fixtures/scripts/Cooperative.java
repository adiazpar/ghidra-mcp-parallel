import ghidra.app.script.GhidraScript;
public class Cooperative extends GhidraScript {
    @Override public void run() throws Exception {
        long millis=Long.parseLong(getScriptArgs()[0]);
        long stop=System.nanoTime()+millis*1000000;
        while(System.nanoTime()<stop){monitor.checkCancelled();Thread.sleep(10);}
        println("cooperative-done");
    }
}
