import ghidra.app.script.GhidraScript;
public class PromptProbe extends GhidraScript {
    @Override public void run() throws Exception { println("prompt=" + askString("Fixture", "Value")); }
}
