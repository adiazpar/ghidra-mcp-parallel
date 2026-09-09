import ghidra.app.util.headless.HeadlessScript;
public class CheckSaved extends HeadlessScript {
    @Override public void run() throws Exception { println("saved-comment="+getEOLComment(currentProgram.getMinAddress())); }
}
