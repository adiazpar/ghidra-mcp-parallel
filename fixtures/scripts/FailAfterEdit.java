import ghidra.app.script.GhidraScript;
public class FailAfterEdit extends GhidraScript {
    @Override public void run() throws Exception {
        setEOLComment(currentAddress,"script partial effect");
        printerr("before-failure");
        throw new IllegalStateException("fixture failure");
    }
}
