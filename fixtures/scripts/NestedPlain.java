import ghidra.app.script.GhidraScript;
public class NestedPlain extends GhidraScript {
    @Override public void run() { println("plain-nested=" + String.join(",",getScriptArgs())); }
}
