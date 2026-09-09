import ghidra.app.util.headless.HeadlessScript;
public class LifecyclePost extends HeadlessScript {
    @Override public void run() throws Exception {
        println("post-analysis-enabled="+isHeadlessAnalysisEnabled());
        println("post-analysis-timeout="+analysisTimeoutOccurred());
        println("post-functions="+currentProgram.getFunctionManager().getFunctionCount());
    }
}
