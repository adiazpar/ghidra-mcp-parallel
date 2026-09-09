import ghidra.app.util.headless.HeadlessScript;

public class NestedProbe extends HeadlessScript {
    @Override public void run() throws Exception {
        println("nested=" + getStoredHeadlessValue("probe"));
        println("nestedArgs=" + String.join(",", getScriptArgs()));
    }
}
