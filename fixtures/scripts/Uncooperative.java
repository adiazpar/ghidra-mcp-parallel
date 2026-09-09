import ghidra.app.script.GhidraScript;
public class Uncooperative extends GhidraScript {
    @Override public void run() throws Exception { while(true)Thread.sleep(100); }
}
