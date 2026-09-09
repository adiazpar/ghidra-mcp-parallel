import ghidra.app.util.headless.HeadlessScript;
import ghidra.program.util.ProgramSelection;
public class BaselineContext extends HeadlessScript {
    @Override public void run() throws Exception {
        currentAddress=toAddr("140001064");
        currentSelection=new ProgramSelection(currentAddress,currentAddress.add(3));
        runScript("ContextProbe.java",new String[]{"fixture-arg"});
        runScript("jython_probe.py",new String[]{"fixture-arg"});
        runScript("PromptProbe.java",new String[]{});
        println("context-complete");
    }
}
