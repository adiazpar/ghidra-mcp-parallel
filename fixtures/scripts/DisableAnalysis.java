import ghidra.app.util.headless.HeadlessScript;
public class DisableAnalysis extends HeadlessScript {
    @Override public void run() throws Exception { enableHeadlessAnalysis(false); println("disabled="+!isHeadlessAnalysisEnabled()); }
}
